"""API indexes use unique collections; legacy Streamlit helpers stay unchanged."""
from threading import Lock
import uuid


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
        )
        return list(zip(result['documents'][0], result['metadatas'][0]))

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
        collection = client.create_collection('api-' + uuid.uuid4().hex)
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
