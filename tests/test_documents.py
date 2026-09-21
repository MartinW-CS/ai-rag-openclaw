import io
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from support import ApiFixture, FakeIndex, generate, pdf_bytes
from app.api import create_app


class DocumentTests(ApiFixture, unittest.TestCase):
    def setUp(self):
        self.setup_api()

    def test_upload_list_duplicate_and_remove(self):
        self.assertEqual(self.client.get('/documents').json(), [])
        response = self.upload('guide.PDF')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['name'], 'guide.pdf')
        self.assertEqual(response.json()['status'], 'queued')
        self.ready()
        self.assertEqual(self.client.get('/documents').json()[0]['status'], 'indexed')
        original = (self.directory / 'guide.pdf').read_bytes()
        self.assertEqual(self.upload().status_code, 409)
        self.assertEqual((self.directory / 'guide.pdf').read_bytes(), original)
        self.assertEqual(self.client.delete('/documents', params={'filename': 'guide.pdf'}).status_code, 200)
        self.assertEqual(self.client.get('/documents').json(), [])
        self.assertEqual(next((self.directory / '.trash').glob('*/guide.pdf')).read_bytes(), original)
        self.assertEqual(self.client.delete('/documents', params={'filename': 'guide.pdf'}).status_code, 404)

    def test_invalid_files_never_enter_library(self):
        for name, data, status in [('bad.txt', pdf_bytes(), 400), ('../escape.pdf', pdf_bytes(), 400), ('bad.pdf', b'not pdf', 422), ('empty.pdf', pdf_bytes(''), 422)]:
            with self.subTest(name=name):
                self.assertEqual(self.upload(name, data).status_code, status)
        with patch('app.api.MAX_PDF_BYTES', 10):
            self.assertEqual(self.upload().status_code, 413)
        self.assertEqual(self.client.get('/documents').json(), [])

    def test_encrypted_and_symlink_rejected(self):
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100); writer.encrypt('secret')
        buffer = io.BytesIO(); writer.write(buffer)
        self.assertEqual(self.upload(data=buffer.getvalue()).status_code, 422)
        (self.directory / 'link.pdf').symlink_to(self.directory / 'outside')
        self.assertEqual(self.upload('link.pdf').status_code, 400)
        self.assertEqual(self.client.delete('/documents', params={'filename': '../outside.pdf'}).status_code, 400)

    def test_external_changes_are_detected_without_questions(self):
        self.upload(); self.ready()
        first = self.service.current
        (self.directory / 'guide.pdf').write_bytes(pdf_bytes('Changed text from another application.'))
        self.ready()
        self.assertIsNot(first, self.service.current)
        self.assertTrue(first.index.closed)

    def test_second_worker_cannot_own_same_directory(self):
        other = create_app(self.directory, builder=FakeIndex, generator=generate)
        with self.assertRaisesRegex(RuntimeError, 'one worker'):
            with TestClient(other):
                pass
        other.state.retrieval.close()
