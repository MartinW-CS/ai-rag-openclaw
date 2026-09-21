"""Real Chroma collection isolation with tiny deterministic embedding vectors."""
import importlib.util
from pathlib import Path
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch
from support import pdf_bytes
from app.api_index import ApiIndexBuilder


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
            builder = ApiIndexBuilder()
            old, new = builder(directory), builder(directory)
            self.assertNotEqual(old.collection.name, new.collection.name)
            self.assertEqual(TinyEmbedder.instances, 2)  # one builder model + one query model
            self.assertEqual({meta['source'] for _, meta in old.retrieve('Q', ['a.pdf'])}, {'a.pdf'})
            old.close()
            self.assertEqual({meta['source'] for _, meta in new.retrieve('Q', ['b.pdf'])}, {'b.pdf'})
            name, client = new.collection.name, new.client
            new.close()
            self.assertNotIn(name, [collection.name for collection in client.list_collections()])
