"""Streamlit UI for the RAG pipeline."""
import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

from ingest import load_and_chunk_pdfs
from retriever import build_vector_store, retrieve
from generator import ask_claude

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv()

st.set_page_config(page_title="RAG Knowledge Assistant", page_icon="📚")
st.title("AI Knowledge Assistant")
st.caption("Ask questions about your uploaded documents")

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

# Uploader always visible, before setup()
with st.sidebar:
    st.subheader("Upload a PDF")
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf", label_visibility="collapsed")
    if uploaded_file is not None:
        save_path = DATA_DIR / uploaded_file.name
        if not save_path.exists():
            save_path.write_bytes(uploaded_file.getvalue())
            st.success(f"Uploaded: {uploaded_file.name}")
            st.cache_resource.clear()
            st.rerun()
        else:
            st.info(f"{uploaded_file.name} is already indexed.")
    st.divider()

collection, embedder, sources = setup()

# Indexed docs shown after setup()
with st.sidebar:
    st.subheader("Indexed documents")
    for s in sources:
        col1, col2 = st.columns([4, 1])
        col1.write(f"- {s}")
        if col2.button("🗑️", key=s):
            (DATA_DIR / s).unlink(missing_ok=True)
            st.cache_resource.clear()
            st.rerun()
    if collection:
        st.caption(f"{collection.count()} chunks indexed")

if collection is None:
    st.info("Upload a PDF in the sidebar to get started.")
    st.stop()

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