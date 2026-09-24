"""API indexes use unique collections; legacy Streamlit helpers stay unchanged."""
import math
from threading import Lock
import uuid


def cosine_similarity(left, right):
    """Actual cosine similarity, independent of the L2 ranking; undefined for zero vectors."""
    if len(left) != len(right):
        raise ValueError('Embedding dimensions differ')
    left_norm = math.sqrt(math.fsum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(math.fsum(float(value) ** 2 for value in right))
    if left_norm == 0 or right_norm == 0:
        return None
    score = math.fsum(float(a) * float(b) for a, b in zip(left, right)) / (left_norm * right_norm)
    if not math.isfinite(score):
        return None
    return max(-1.0, min(1.0, score))


class ApiIndex:
    def __init__(self, client, collection, embedder, query_lock):
        self.client, self.collection = client, collection
        self.embedder, self.query_lock = embedder, query_lock

    def retrieve(self, question, allowed):
        from .retriever import TOP_K
        # This runs in a bounded, dedicated retrieval executor, never the event loop.
        with self.query_lock:
            embedding = self.embedder.encode([question]).tolist()
        result = self.collection.query(
            query_embeddings=embedding,
            n_results=min(TOP_K, self.collection.count()),
            where={'source': {'$in': allowed}},
            include=['documents', 'metadatas', 'distances', 'embeddings'],
        )
        return [
            (text, {**metadata, 'chunk_id': chunk_id, 'index_id': self.collection.name,
                    'distance': float(distance),
                    'similarity_score': cosine_similarity(embedding[0], vector)})
            for chunk_id, text, metadata, distance, vector in zip(
                result['ids'][0], result['documents'][0], result['metadatas'][0],
                result['distances'][0], result['embeddings'][0], strict=True,
            )
        ]

    def close(self):
        self.client.delete_collection(self.collection.name)


class ApiIndexBuilder:
    def __init__(self):
        self.build_embedder = None
        self.query_embedder = None
        self.query_lock = Lock()

    def __call__(self, directory):
        import chromadb
        from sentence_transformers import SentenceTransformer
        from .ingest import load_and_chunk_pdfs
        from .retriever import EMBED_MODEL

        chunks = load_and_chunk_pdfs(directory)
        if not chunks:
            raise ValueError('No extractable PDF text')
        # Separate reusable models keep background embedding off the query model lock.
        if self.build_embedder is None:
            self.build_embedder = SentenceTransformer(EMBED_MODEL)
        if self.query_embedder is None:
            self.query_embedder = SentenceTransformer(EMBED_MODEL)
        client = chromadb.EphemeralClient()
        collection = client.create_collection('api-' + uuid.uuid4().hex, metadata={'hnsw:space': 'l2'})
        try:
            for offset in range(0, len(chunks), 128):
                batch = chunks[offset:offset + 128]
                texts = [chunk['text'] for chunk in batch]
                collection.add(
                    ids=[f'chunk-{i}' for i in range(offset, offset + len(batch))],
                    documents=texts,
                    embeddings=self.build_embedder.encode(texts).tolist(),
                    metadatas=[{'source': chunk['source'], 'page': chunk['page']} for chunk in batch],
                )
            return ApiIndex(client, collection, self.query_embedder, self.query_lock)
        except Exception:
            client.delete_collection(collection.name)
            raise
