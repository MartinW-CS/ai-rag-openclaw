import asyncio
import unittest
from unittest.mock import patch, AsyncMock

from support import ApiFixture, pdf_bytes


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
        data = response.json()
        self.assertEqual(data['answer'], 'Grounded answer')
        self.assertEqual(data['sources'], [{'source': 'guide.pdf', 'page': 1}])
        self.assertEqual(data['retrieval']['distance_metric'], 'squared_l2')
        self.assertEqual(data['retrieval']['similarity_metric'], 'cosine')
        self.assertEqual(data['retrieval']['chunks'][0], {
            'rank': 1, 'chunk_id': 'chunk-0', 'index_id': 'test-index',
            'source': 'guide.pdf', 'page': 1, 'text': 'A document about retrieval.',
            'distance': 0.0, 'similarity_score': 1.0,
        })
        self.assertEqual([chunk['text'] for chunk in data['retrieval']['chunks']],
                         [text for text, _ in generator.call_args.args[1]])
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


    def test_inspector_preserves_chunks_but_sources_are_deduplicated(self):
        self.upload(data=pdf_bytes('retrieval context ' * 80))
        self.ready()
        generator = AsyncMock(return_value='Answer')
        self.app.state.generator = generator
        data = self.client.post('/ask', json={'question': 'Q'}).json()
        chunks = data['retrieval']['chunks']
        self.assertGreater(len(chunks), 1)
        self.assertEqual([chunk['rank'] for chunk in chunks], list(range(1, len(chunks) + 1)))
        self.assertEqual(len({chunk['chunk_id'] for chunk in chunks}), len(chunks))
        self.assertEqual(len(data['sources']), 1)
        self.assertEqual([chunk['text'] for chunk in chunks], [text for text, _ in generator.call_args.args[1]])
        self.assertNotIn('embeddings', data['retrieval'])

    def test_top_k_validation_default_and_generation_context(self):
        self.upload(data=pdf_bytes('retrieval context ' * 400)); self.ready()
        generator = AsyncMock(return_value='Answer')
        self.app.state.generator = generator
        for value in (None, 2, 4, 6, 8):
            body = {'question': 'Q'}
            if value is not None:
                body['top_k'] = value
            response = self.client.post('/ask', json=body)
            self.assertEqual(response.status_code, 200)
            data = response.json()['retrieval']
            self.assertEqual(data['top_k'], value or 4)
            self.assertEqual(len(data['chunks']), value or 4)
            self.assertEqual([chunk['text'] for chunk in data['chunks']], [text for text, _ in generator.call_args.args[1]])
        for invalid in (0, 1, 3, 5, 7, 10, -2, True, '4', 4.0, None):
            self.assertEqual(self.client.post('/ask', json={'question': 'Q', 'top_k': invalid}).status_code, 422)
        self.client.delete('/documents', params={'filename': 'guide.pdf'})
        self.upload(data=pdf_bytes('Short document.')); self.ready()
        data = self.client.post('/ask', json={'question': 'Q', 'top_k': 8}).json()['retrieval']
        self.assertEqual(data['top_k'], 8)
        self.assertEqual(len(data['chunks']), 1)
