"""End-to-end RAG pipeline: orchestrates ingest -> retrieve -> generate."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from ingest import load_and_chunk_pdfs
from retriever import build_vector_store, retrieve
from generator import ask_claude

DATA_DIR = Path(__file__).parent / "data"

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

    print("\nReady. Type a question (or 'quit' to exit).\n")
    while True:
        try:
            query = input("Q: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            continue
        if query.lower() in {"quit", "exit", "q"}:
            break

        retrieved = retrieve(collection, embedder, query)
        print()
        print(ask_claude(query, retrieved))
        print()

if __name__ == "__main__":
    main()