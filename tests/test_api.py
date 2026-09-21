"""API contract tests without model downloads or external API calls."""
import os
import sys
import unittest
from types import ModuleType
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from app import api


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.env = patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_health_without_key_or_index(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(api, "get_index") as index:
            self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
            index.assert_not_called()

    def test_invalid_question(self):
        for body in ({}, {"question": ""}, {"question": "  "}, {"question": 42}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/ask", json=body).status_code, 422)

    def test_missing_key(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.client.post("/ask", json={"question": "Q"}).status_code, 503)

    def test_reuses_retrieval_and_generation(self):
        retriever = ModuleType("app.retriever")
        retriever.TOP_K = 4
        retriever.retrieve = Mock(return_value=[("text", {"source": "a.pdf", "page": 1})] * 2)
        generator = ModuleType("app.generator")
        generator.ask_claude = Mock(return_value="Grounded answer")
        collection, embedder = Mock(), Mock()
        collection.count.return_value = 2
        with patch.dict(sys.modules, {"app.retriever": retriever, "app.generator": generator}), patch.object(api, "get_index", return_value=(collection, embedder)):
            response = self.client.post("/ask", json={"question": " Q "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"answer": "Grounded answer", "sources": [{"source": "a.pdf", "page": 1}]})
        retriever.retrieve.assert_called_once_with(collection, embedder, "Q", k=2)
        generator.ask_claude.assert_called_once_with("Q", retriever.retrieve.return_value)

    def test_empty_index_retries_and_success_is_cached(self):
        ingest, retriever = ModuleType("app.ingest"), ModuleType("app.retriever")
        ingest.load_and_chunk_pdfs = Mock(side_effect=[[], [{"text": "text"}]])
        retriever.build_vector_store = Mock(return_value=(Mock(), Mock()))
        with patch.dict(sys.modules, {"app.ingest": ingest, "app.retriever": retriever}), patch.object(api, "_index", None):
            self.assertEqual(self.client.post("/ask", json={"question": "Q"}).status_code, 503)
            first = api.get_index()
            self.assertIs(first, api.get_index())
            retriever.build_vector_store.assert_called_once()

    def test_internal_error_is_not_exposed(self):
        with patch.object(api, "answer_question", side_effect=RuntimeError("private detail")), self.assertLogs(api.logger, level="ERROR"):
            response = self.client.post("/ask", json={"question": "Q"})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private detail", response.text)
