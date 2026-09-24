"""Local, single-worker API with background indexing and bounded admission."""
import asyncio
from contextlib import asynccontextmanager
import fcntl
import errno
import stat
from urllib.parse import quote
import io
import logging
import os
from pathlib import Path
import tempfile
from typing import Annotated, Literal
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from starlette.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field, FiniteFloat, StringConstraints

from .concurrency import AdmissionMiddleware, BoundedExecutor, Busy
from .index_service import IndexService, IndexUnavailable

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / 'data'
MAX_PDF_BYTES = 10 * 1024 * 1024


TopK = Annotated[int, Field(strict=True, ge=2, le=8, multiple_of=2)]


class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
    top_k: TopK = 4


class Source(BaseModel):
    source: str
    page: int


class RetrievedChunk(BaseModel):
    rank: int = Field(ge=1)
    chunk_id: str
    index_id: str
    source: str
    page: int
    text: str
    distance: FiniteFloat
    similarity_score: FiniteFloat | None


class RetrievalDetails(BaseModel):
    top_k: TopK = 4
    distance_metric: Literal['squared_l2'] = 'squared_l2'
    similarity_metric: Literal['cosine'] = 'cosine'
    chunks: list[RetrievedChunk]


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    retrieval: RetrievalDetails


class Document(BaseModel):
    name: str
    size: int
    status: str


def positive_env(name, default):
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f'{name} must be positive')
    return value


def safe_document_path(directory, filename):
    if (not filename or filename.startswith('.') or '/' in filename or '\\' in filename
            or any(ord(char) < 32 for char in filename) or len(filename.encode('utf-8')) > 200
            or not filename.endswith('.pdf')):
        raise HTTPException(400, '请使用有效的 PDF 文件名。')
    path = directory / filename
    if path.is_symlink():
        raise HTTPException(400, '不支持符号链接。')
    return path


def create_app(directory=DATA_DIR, *, builder=None, generator=None, ask_limit=None,
               retrieval_workers=None, ask_timeout=60.0, poll_seconds=2):
    from .api_index import ApiIndexBuilder
    directory = Path(directory)
    service = IndexService(directory, builder or ApiIndexBuilder(), poll_seconds=poll_seconds)
    retrieval = BoundedExecutor(retrieval_workers or positive_env('RAG_RETRIEVAL_WORKERS', 2))

    @asynccontextmanager
    async def lifespan(application):
        directory.mkdir(parents=True, exist_ok=True)
        ownership = (directory / '.api.lock').open('a')
        try:
            try:
                fcntl.flock(ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('This API supports one worker per document directory. Stop the other worker first.') from None
            if generator is None:
                from .async_generator import AsyncGenerator
                application.state.generator = AsyncGenerator()
            else:
                application.state.generator = generator
            service.start()
            try:
                yield
            finally:
                # Shutdown happens off the event loop and drains admitted CPU work.
                await asyncio.to_thread(retrieval.close)
                await asyncio.to_thread(service.stop)
                close = getattr(application.state.generator, 'close', None)
                if close is not None:
                    await close()
        finally:
            ownership.close()

    application = FastAPI(title='RAG Knowledge Assistant', lifespan=lifespan)
    application.state.index = service
    application.state.retrieval = retrieval
    application.add_middleware(AdmissionMiddleware,
                              ask_limit=ask_limit or positive_env('RAG_MAX_ASK', 8),
                              upload_limit=positive_env('RAG_MAX_UPLOAD', 2))

    @application.get('/health')
    async def health():
        return {'status': 'ok'}

    def retrieve_question(question, top_k):
        with service.lease() as (version, allowed):
            chunks = version.index.retrieve(question, allowed, top_k)
            return service.filter_current(chunks, version.signature), version.signature

    @application.post('/ask', response_model=AskResponse)
    async def ask(request: AskRequest):
        if not os.getenv('ANTHROPIC_API_KEY'):
            raise HTTPException(503, 'ANTHROPIC_API_KEY is not configured.')
        try:
            async with asyncio.timeout(ask_timeout):
                chunks, signature = await retrieval.run(retrieve_question, request.question, request.top_k)
                if not chunks:
                    raise IndexUnavailable('没有可用的已索引内容，请等待索引更新。')
                answer = await application.state.generator(request.question, chunks)
                # Do not return an answer based on a removed/replaced document.
                if service.filter_current(chunks, signature) != chunks:
                    raise HTTPException(409, '回答期间文档发生变化，请重新提问。')
                sources = dict.fromkeys((meta['source'], meta['page']) for _, meta in chunks)
                return AskResponse(
                    answer=answer,
                    sources=[Source(source=name, page=page) for name, page in sources],
                    retrieval=RetrievalDetails(top_k=request.top_k, chunks=[
                        RetrievedChunk(rank=rank, text=text, **meta)
                        for rank, (text, meta) in enumerate(chunks, start=1)
                    ]),
                )
        except HTTPException:
            raise
        except Busy as error:
            raise HTTPException(429, str(error), headers={'Retry-After': '2'}) from None
        except IndexUnavailable as error:
            raise HTTPException(503, str(error), headers={'Retry-After': '2'}) from None
        except TimeoutError:
            raise HTTPException(504, '回答超时，请稍后重试。') from None
        except Exception as error:
            from anthropic import APITimeoutError, RateLimitError, APIError
            if isinstance(error, APITimeoutError):
                raise HTTPException(504, '模型服务超时，请稍后重试。') from None
            if isinstance(error, RateLimitError):
                raise HTTPException(429, '模型服务繁忙，请稍后重试。', headers={'Retry-After': '5'}) from None
            if isinstance(error, APIError):
                logger.exception('Model service failed')
                raise HTTPException(502, '模型服务暂时不可用，请稍后重试。') from None
            logger.exception('RAG request failed')
            raise HTTPException(500, 'Unable to answer the question. Check server logs.') from None

    @application.get('/documents', response_model=list[Document])
    def list_documents():
        return service.documents()

    @application.get('/documents/{filename:path}/file')
    def document_file(filename: str):
        path = safe_document_path(directory, filename)
        # Bind the response to an opened file, not a path that can be swapped later.
        try:
            with service.condition:
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                stream = os.fdopen(descriptor, 'rb')
                try:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode):
                        raise HTTPException(400, '只能预览普通 PDF 文件。')
                    if info.st_size > MAX_PDF_BYTES:
                        raise HTTPException(413, 'PDF 不能超过 10 MB。')
                    if stream.read(5) != b'%PDF-':
                        raise HTTPException(422, '文件不是有效的 PDF。')
                    stream.seek(0)
                except BaseException:
                    stream.close()
                    raise
        except FileNotFoundError:
            raise HTTPException(404, '文档不存在或已被移除。') from None
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.ENOTDIR):
                raise HTTPException(400, '无效的文档路径。') from None
            raise

        def body():
            try:
                while block := stream.read(65536):
                    yield block
            finally:
                stream.close()

        return StreamingResponse(
            body(), media_type='application/pdf',
            headers={'Content-Length': str(info.st_size), 'Cache-Control': 'no-store',
                     'X-Content-Type-Options': 'nosniff',
                     'Content-Disposition': "inline; filename*=UTF-8''" + quote(filename, safe='')},
            background=BackgroundTask(stream.close),
        )

    @application.post('/index/retry', status_code=202)
    def retry_index():
        service.retry()
        return {'status': 'queued'}

    @application.post('/documents', response_model=Document, status_code=201)
    def upload_document(file: UploadFile):
        try:
            filename = file.filename or ''
            if filename.lower().endswith('.pdf'):
                filename = filename[:-4] + '.pdf'
            path = safe_document_path(directory, filename)
            contents = file.file.read(MAX_PDF_BYTES + 1)
        finally:
            file.file.close()
        if len(contents) > MAX_PDF_BYTES:
            raise HTTPException(413, 'PDF 不能超过 10 MB。')
        from pypdf import PdfReader
        try:
            if not contents.startswith(b'%PDF-'):
                raise ValueError('Not a PDF')
            reader = PdfReader(io.BytesIO(contents))
            if reader.is_encrypted or not any((page.extract_text() or '').strip() for page in reader.pages):
                raise ValueError('Encrypted PDF or no extractable text')
        except Exception:
            raise HTTPException(422, '请上传包含可提取文字的有效 PDF；暂不支持加密或纯扫描文档。') from None
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.tmp') as temp:
            temp.write(contents)
            temp.flush()
            with service.condition:
                try:
                    os.link(temp.name, path)
                except FileExistsError:
                    raise HTTPException(409, '同名文档已存在，请重命名后上传。') from None
                service.changed()
        return Document(name=filename, size=len(contents), status='queued')

    @application.delete('/documents')
    def delete_document(filename: str):
        path = safe_document_path(directory, filename)
        with service.condition:
            if not path.is_file():
                raise HTTPException(404, '文档不存在。')
            trash = directory / '.trash' / uuid.uuid4().hex
            trash.mkdir(parents=True)
            path.rename(trash / filename)
            service.changed()
        return {'status': 'removed', 'name': filename}

    return application


app = create_app()
