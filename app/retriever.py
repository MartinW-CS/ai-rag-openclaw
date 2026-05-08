"""Vector store and retrieval via ChromaDB + sentence-transformers."""
import chromadb
from sentence_transformers import SentenceTransformer

EMBED_MODEL = "all-MiniLM-L6-v2"
TOP_K = 4
COLLECTION_NAME = "rag_mvp"

def build_vector_store(chunks):
    """Embed chunks and load them into an in-memory Chroma collection."""
    embedder = SentenceTransformer(EMBED_MODEL)
    client = chromadb.Client()
    if any(c.name == COLLECTION_NAME for c in client.list_collections()):
        client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(COLLECTION_NAME)

    texts = [c["text"] for c in chunks]
    embeddings = embedder.encode(texts).tolist()
    ids = [f"chunk-{i}" for i in range(len(chunks))]
    metadatas = [{"source": c["source"], "page": c["page"]} for c in chunks]

    collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
    return collection, embedder

def retrieve(collection, embedder, query: str, k: int = TOP_K):
    """Return the top-k (text, metadata) tuples most similar to the query."""
    q_emb = embedder.encode([query]).tolist()
    results = collection.query(query_embeddings=q_emb, n_results=k)
    return list(zip(results["documents"][0], results["metadatas"][0]))