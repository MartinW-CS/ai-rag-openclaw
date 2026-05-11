"""Streamlit UI for the RAG pipeline."""
import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Make sibling modules importable when run via `streamlit run app/streamlit_app.py`
sys.path.insert(0, str(Path(__file__).parent))

from ingest import load_and_chunk_pdfs
from retriever import build_vector_store, retrieve
from generator import ask_claude

DATA_DIR = Path(__file__).parent / "data"

load_dotenv()

st.set_page_config(page_title="RAG Knowledge Assistant", page_icon="📚")
st.title("AI Knowledge Assistant")
st.caption("Ask questions about the documents in app/data/")

if not os.getenv("ANTHROPIC_API_KEY"):
    st.error("ANTHROPIC_API_KEY not set in .env")
    st.stop()

@st.cache_resource(show_spinner="Loading documents and building vector store...")
def setup():
    chunks = load_and_chunk_pdfs(DATA_DIR)
    if not chunks:
        return None, None, []
    collection, embedder = build_vector_store(chunks)
    sources = sorted({c["source"] for c in chunks})
    return collection, embedder, sources

collection, embedder, sources = setup()
if collection is None:
    st.warning("No PDFs found in app/data/. Add a PDF and reload the page.")
    st.stop()

with st.sidebar:
    st.subheader("Indexed documents")
    for s in sources:
        st.write(f"- {s}")
    st.caption(f"{collection.count()} chunks indexed")

query = st.text_input("Your question", placeholder="What is RAG?")
if query:
    with st.spinner("Retrieving and asking Claude..."):
        retrieved = retrieve(collection, embedder, query)
        answer = ask_claude(query, retrieved)
    st.markdown(answer)

    with st.expander("Show retrieved chunks"):
        for i, (text, meta) in enumerate(retrieved, start=1):
            st.markdown(f"**Chunk {i}** — `{meta['source']}`, page {meta['page']}")
            st.text(text)