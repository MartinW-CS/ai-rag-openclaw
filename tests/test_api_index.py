"""Real Chroma collection isolation with tiny deterministic embedding vectors."""
import importlib.util
import math
from pathlib import Path
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch
from support import pdf_bytes
from app.api_index import ApiIndexBuilder, cosine_similarity


class VectorBatch(list):
    def tolist(self):
        return list(self)


class TinyEmbedder:
    instances = 0

    def __init__(self, model):
        type(self).instances += 1

    def encode(self, texts):
        return VectorBatch([[1.0, float(len(text) % 7) / 7.0, 0.5] for text in texts])


@unittest.skipUnless(importlib.util.find_spec('chromadb'), 'Install chromadb for the integration test')
class ChromaIntegrationTests(unittest.TestCase):
    def test_versions_filters_model_reuse_and_collection_cleanup(self):
        sentence = ModuleType('sentence_transformers')
        sentence.SentenceTransformer = TinyEmbedder
        retriever = ModuleType('app.retriever')
        retriever.EMBED_MODEL, retriever.TOP_K = 'tiny-test', 4
        TinyEmbedder.instances = 0
        with tempfile.TemporaryDirectory() as directory, patch.dict('sys.modules', {'sentence_transformers': sentence, 'app.retriever': retriever}):
            directory = Path(directory)
            (directory / 'a.pdf').write_bytes(pdf_bytes('First source.'))
            (directory / 'b.pdf').write_bytes(pdf_bytes('Second source.'))
            for i in range(8):
                (directory / f'extra-{i}.pdf').write_bytes(pdf_bytes(f'Extra source {i}.'))
            builder = ApiIndexBuilder()
            old, new = builder(directory), builder(directory)
            self.assertNotEqual(old.collection.name, new.collection.name)
            self.assertEqual(TinyEmbedder.instances, 2)  # one builder model + one query model
            allowed = [path.name for path in directory.glob('*.pdf')]
            for top_k in (2, 4, 6, 8):
                self.assertEqual(len(old.retrieve('Q', allowed, top_k)), top_k)
            self.assertEqual(len(old.retrieve('Q', ['a.pdf'], 8)), 1)
            self.assertEqual({meta['source'] for _, meta in old.retrieve('Q', ['a.pdf'])}, {'a.pdf'})
            matches = old.retrieve('Q', ['a.pdf', 'b.pdf'])
            distances = [meta['distance'] for _, meta in matches]
            self.assertEqual(distances, sorted(distances))
            query_vector = TinyEmbedder('test').encode(['Q'])[0]
            for text, meta in matches:
                vector = TinyEmbedder('test').encode([text])[0]
                expected_l2 = sum((a - b) ** 2 for a, b in zip(query_vector, vector))
                expected_cosine = sum(a * b for a, b in zip(query_vector, vector)) / math.sqrt(sum(a*a for a in query_vector) * sum(b*b for b in vector))
                self.assertAlmostEqual(meta['distance'], expected_l2, places=5)
                self.assertAlmostEqual(meta['similarity_score'], expected_cosine, places=5)
                self.assertEqual(meta['index_id'], old.collection.name)
                self.assertTrue(meta['chunk_id'].startswith('chunk-'))
            old.close()
            self.assertEqual({meta['source'] for _, meta in new.retrieve('Q', ['b.pdf'])}, {'b.pdf'})
            name, client = new.collection.name, new.client
            new.close()
            self.assertNotIn(name, [collection.name for collection in client.list_collections()])


class SimilarityTests(unittest.TestCase):
    def test_cosine_is_not_a_distance_or_probability(self):
        self.assertAlmostEqual(cosine_similarity([2, 0], [8, 0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 3]), 0.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [-2, 0]), -1.0)
        self.assertIsNone(cosine_similarity([0, 0], [1, 2]))
        self.assertIsNone(cosine_similarity([1, 2], [0, 0]))
        with self.assertRaises(ValueError):
            cosine_similarity([1], [1, 2])
