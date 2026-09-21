"""Minimal HTTP interface over the existing PDF retrieval and generation code."""
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, StringConstraints

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
app = FastAPI(title="RAG Knowledge Assistant")
logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
_index = None
_index_lock = Lock()


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
    global _index
    with _index_lock:
        if _index is None:
            from .ingest import load_and_chunk_pdfs

            chunks = load_and_chunk_pdfs(DATA_DIR)
            if not chunks:
                raise HTTPException(503, "No PDF text found. Add PDFs to app/data/.")
            from .retriever import build_vector_store

            _index = build_vector_store(chunks)
        return _index


def answer_question(question: str) -> AskResponse:
    collection, embedder = get_index()
    from .retriever import TOP_K, retrieve
    from .generator import ask_claude

    retrieved = retrieve(collection, embedder, question, k=min(TOP_K, collection.count()))
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
