"""
Phase 1 MVP: single-script RAG pipeline.
Flow: ingest PDFs -> chunk -> embed -> store in Chroma -> retrieve -> ask Claude.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader
import chromadb
from sentence_transformers import SentenceTransformer
from anthropic import Anthropic

# ---------- Config ----------
DATA_DIR = Path(__file__).parent / "data"
CHUNK_SIZE = 500          # characters per chunk
CHUNK_OVERLAP = 50
TOP_K = 4
EMBED_MODEL = "all-MiniLM-L6-v2"
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = """You are a retrieval-augmented assistant. Answer using ONLY the provided context.
- Ground answers strictly in the context. Do not introduce outside knowledge.
- If the context is insufficient, explicitly say so.
- Always cite sources in the format: (Source: <file_name>, Page <page_number>).

Output format:
Answer:
<final answer>

Sources:
- <source 1>
- <source 2>
"""

# ---------- 1. Ingest: load PDFs, split into chunks ----------
def load_and_chunk_pdfs(data_dir: Path):
    chunks = []
    for pdf_path in sorted(data_dir.glob("*.pdf")):
        reader = PdfReader(str(pdf_path))
        for page_num, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            i = 0
            while i < len(text):
                chunks.append({
                    "text": text[i : i + CHUNK_SIZE],
                    "source": pdf_path.name,
                    "page": page_num,
                })
                i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks

# ---------- 2-3. Embed chunks and store in Chroma ----------
def build_vector_store(chunks):
    embedder = SentenceTransformer(EMBED_MODEL)
    client = chromadb.Client()  # in-memory store for MVP
    if any(c.name == "rag_mvp" for c in client.list_collections()):
        client.delete_collection("rag_mvp")
    collection = client.create_collection("rag_mvp")

    texts = [c["text"] for c in chunks]
    embeddings = embedder.encode(texts).tolist()
    ids = [f"chunk-{i}" for i in range(len(chunks))]
    metadatas = [{"source": c["source"], "page": c["page"]} for c in chunks]

    collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
    return collection, embedder

# ---------- 4. Retrieve top-k chunks for the query ----------
def retrieve(collection, embedder, query: str, k: int = TOP_K):
    q_emb = embedder.encode([query]).tolist()
    results = collection.query(query_embeddings=q_emb, n_results=k)
    return list(zip(results["documents"][0], results["metadatas"][0]))

# ---------- 5. Ask Claude with the retrieved context ----------
def ask_claude(query, retrieved):
    context = "\n\n".join(
        f"[Chunk {i} | Source: {m['source']}, Page {m['page']}]\n{doc}"
        for i, (doc, m) in enumerate(retrieved, start=1)
    )
    user_msg = f"Context:\n{context}\n\nQuestion: {query}"

    client = Anthropic()  # reads ANTHROPIC_API_KEY from environment
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text

# ---------- Main ----------
def main():
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY not set in .env")

    print("Loading and chunking PDFs...")
    chunks = load_and_chunk_pdfs(DATA_DIR)
    print(f"  -> {len(chunks)} chunks from {DATA_DIR}")
    if not chunks:
        sys.exit("No chunks found. Put a PDF in app/data/ first.")

    print("Building vector store...")
    collection, embedder = build_vector_store(chunks)
    print(f"  -> {collection.count()} chunks indexed")

    query = input("\nAsk a question: ").strip()
    if not query:
        return

    print("\nRetrieving relevant chunks...")
    retrieved = retrieve(collection, embedder, query)

    print("\nAsking Claude...\n")
    print(ask_claude(query, retrieved))

if __name__ == "__main__":
    main()