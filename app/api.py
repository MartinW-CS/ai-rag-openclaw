"""Minimal HTTP interface over the existing PDF retrieval and generation code."""
import logging
import os
import io
import tempfile
import uuid
from pathlib import Path
from threading import RLock
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel, StringConstraints

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
app = FastAPI(title="RAG Knowledge Assistant")
logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
_index = None
_index_lock = RLock()
_index_signature = None
MAX_PDF_BYTES = 10 * 1024 * 1024


class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Source(BaseModel):
    source: str
    page: int


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]


def get_index():
    """Build once per process; retry after a failed or empty initialization."""
    global _index, _index_signature
    with _index_lock:
        signature = document_signature()
        if _index is None or signature != _index_signature:
            _index = None
            _index_signature = None
            from .ingest import load_and_chunk_pdfs

            chunks = load_and_chunk_pdfs(DATA_DIR)
            if not chunks:
                raise HTTPException(503, "No PDF text found. Add PDFs to app/data/.")
            from .retriever import build_vector_store

            _index = build_vector_store(chunks)
            _index_signature = signature
        return _index


def answer_question(question: str) -> AskResponse:
    # Collection replacement must not race a query against the previous index.
    with _index_lock:
        collection, embedder = get_index()
        from .retriever import TOP_K, retrieve

        retrieved = retrieve(collection, embedder, question, k=min(TOP_K, collection.count()))
    from .generator import ask_claude

    answer = ask_claude(question, retrieved)
    sources = dict.fromkeys((meta["source"], meta["page"]) for _, meta in retrieved)
    return AskResponse(
        answer=answer,
        sources=[Source(source=source, page=page) for source, page in sources],
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness only: does not load embeddings or contact Claude."""
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY is not configured.")
    try:
        return answer_question(request.question)
    except HTTPException:
        raise
    except Exception:
        logger.exception("RAG request failed")
        raise HTTPException(500, "Unable to answer the question. Check server logs.") from None


class Document(BaseModel):
    name: str
    size: int
    status: str


def pdf_paths():
    return sorted(path for path in DATA_DIR.glob("*.pdf") if path.is_file() and not path.is_symlink())


def document_signature():
    return tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in pdf_paths())


def safe_document_path(filename: str):
    if (not filename or filename.startswith(".") or "/" in filename or "\\" in filename
            or any(ord(char) < 32 for char in filename) or len(filename.encode("utf-8")) > 200
            or not filename.endswith(".pdf")):
        raise HTTPException(400, "请使用有效的 PDF 文件名。")
    path = DATA_DIR / filename
    if path.is_symlink():
        raise HTTPException(400, "不支持符号链接。")
    return path


@app.get("/documents", response_model=list[Document])
def list_documents():
    with _index_lock:
        indexed = _index is not None and document_signature() == _index_signature
        return [Document(name=path.name, size=path.stat().st_size,
                         status="indexed" if indexed else "pending") for path in pdf_paths()]


@app.post("/documents", response_model=Document, status_code=201)
def upload_document(file: UploadFile):
    filename = file.filename or ""
    if filename.lower().endswith(".pdf"):
        filename = filename[:-4] + ".pdf"
    path = safe_document_path(filename)
    try:
        contents = file.file.read(MAX_PDF_BYTES + 1)
    finally:
        file.file.close()
    if len(contents) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF 不能超过 10 MB。")
    from pypdf import PdfReader
    try:
        if not contents.startswith(b"%PDF-"):
            raise ValueError("Not a PDF")
        reader = PdfReader(io.BytesIO(contents))
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF")
        if not any((page.extract_text() or "").strip() for page in reader.pages):
            raise ValueError("No extractable text")
    except Exception:
        raise HTTPException(422, "请上传包含可提取文字的有效 PDF；暂不支持加密或纯扫描文档。") from None
    with _index_lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Publish a complete file atomically, without overwriting duplicate names.
        with tempfile.NamedTemporaryFile(dir=DATA_DIR, suffix=".tmp") as temp:
            temp.write(contents)
            temp.flush()
            try:
                os.link(temp.name, path)
            except FileExistsError:
                raise HTTPException(409, "同名文档已存在，请重命名后上传。") from None
    return Document(name=filename, size=len(contents), status="pending")


@app.delete("/documents")
def delete_document(filename: str):
    path = safe_document_path(filename)
    with _index_lock:
        if not path.is_file():
            raise HTTPException(404, "文档不存在。")
        trash = DATA_DIR / ".trash" / uuid.uuid4().hex
        trash.mkdir(parents=True)
        path.rename(trash / filename)
    return {"status": "removed", "name": filename}
