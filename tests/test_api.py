import asyncio
import unittest
from unittest.mock import patch, AsyncMock

from support import ApiFixture


class ApiTests(ApiFixture, unittest.TestCase):
    def setUp(self):
        self.setup_api()

    def test_health_without_key_or_index(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(self.client.get('/health').json(), {'status': 'ok'})

    def test_invalid_question(self):
        for body in ({}, {'question': ''}, {'question': '  '}, {'question': 42}, {'question': 'a' * 8001}):
            with self.subTest(body=str(body)[:40]):
                self.assertEqual(self.client.post('/ask', json=body).status_code, 422)

    def test_missing_key_and_unready_index(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(self.client.post('/ask', json={'question': 'Q'}).status_code, 503)
        response = self.client.post('/ask', json={'question': 'Q'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['retry-after'], '2')

    def test_background_index_answer_and_sources(self):
        self.assertEqual(self.upload().status_code, 201)
        self.ready()
        generator = AsyncMock(return_value='Grounded answer')
        self.app.state.generator = generator
        response = self.client.post('/ask', json={'question': ' Q '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'answer': 'Grounded answer', 'sources': [{'source': 'guide.pdf', 'page': 1}]})
        self.assertEqual(generator.call_args.args[0], 'Q')

    def test_internal_error_is_not_exposed(self):
        self.upload(); self.ready()
        self.app.state.generator = AsyncMock(side_effect=RuntimeError('private detail'))
        with self.assertLogs('app.api', level='ERROR'):
            response = self.client.post('/ask', json={'question': 'Q'})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('private detail', response.text)

    def test_body_limit_before_validation(self):
        self.assertEqual(self.client.post('/ask', content=b'x' * 33000).status_code, 413)
        def chunks():
            yield b'x' * 20000
            yield b'x' * 20000
        self.assertEqual(self.client.post('/ask', content=chunks()).status_code, 413)
