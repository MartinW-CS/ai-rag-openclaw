"""Document lifecycle tests with real PDFs and an isolated temporary library."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import ModuleType
import sys

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from app import api


def pdf_bytes(text='A document about retrieval.'):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(f'BT /F1 12 Tf 20 200 Td ({text}) Tj ET'.encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class DocumentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        for target, value in [('DATA_DIR', self.directory), ('_index', None), ('_index_signature', None)]:
            patcher = patch.object(api, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(api.app)

    def upload(self, name='guide.pdf', data=None):
        return self.client.post('/documents', files={'file': (name, data if data is not None else pdf_bytes(), 'application/pdf')})

    def test_upload_list_duplicate_and_remove(self):
        self.assertEqual(self.client.get('/documents').json(), [])
        response = self.upload('guide.PDF')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['name'], 'guide.pdf')
        self.assertEqual(self.client.get('/documents').json()[0]['status'], 'pending')
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
        with patch.object(api, 'MAX_PDF_BYTES', 10):
            self.assertEqual(self.upload().status_code, 413)
        self.assertEqual(self.client.get('/documents').json(), [])

    def test_encrypted_and_symlink_rejected(self):
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100); writer.encrypt('secret')
        buffer = io.BytesIO(); writer.write(buffer)
        self.assertEqual(self.upload(data=buffer.getvalue()).status_code, 422)
        (self.directory / 'link.pdf').symlink_to(self.directory / 'outside')
        self.assertEqual(self.upload('link.pdf').status_code, 400)
        self.assertEqual(self.client.delete('/documents', params={'filename': '../outside.pdf'}).status_code, 400)

    def test_mutations_and_external_changes_refresh_index(self):
        retriever = ModuleType('app.retriever')
        retriever.build_vector_store = Mock(side_effect=lambda chunks: (Mock(), Mock()))
        with patch.dict(sys.modules, {'app.retriever': retriever}):
            self.upload()
            first = api.get_index()
            self.assertIs(first, api.get_index())
            self.assertEqual(self.client.get('/documents').json()[0]['status'], 'indexed')
            self.upload('second.pdf')
            self.assertTrue(all(item['status'] == 'pending' for item in self.client.get('/documents').json()))
            self.assertIsNot(first, api.get_index())
            self.client.delete('/documents', params={'filename': 'second.pdf'})
            api.get_index()
            (self.directory / 'guide.pdf').write_bytes(pdf_bytes('Changed text from another application.'))
            api.get_index()
            self.assertEqual(retriever.build_vector_store.call_count, 4)
            self.client.delete('/documents', params={'filename': 'guide.pdf'})
            with self.assertRaises(api.HTTPException) as context:
                api.get_index()
            self.assertEqual(context.exception.status_code, 503)
