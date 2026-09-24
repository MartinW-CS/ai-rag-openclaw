import os
import unittest
from urllib.parse import quote
from unittest.mock import patch

from support import ApiFixture, pdf_bytes


class PdfPreviewTests(ApiFixture, unittest.TestCase):
    def setUp(self):
        self.setup_api()

    def test_pdf_bytes_headers_and_unicode_filename(self):
        name = '报告 #1.pdf'
        data = pdf_bytes('PDF preview page one.')
        self.assertEqual(self.upload(name, data).status_code, 201)
        response = self.client.get(f'/documents/{quote(name, safe="")}/file')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, data)
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(int(response.headers['content-length']), len(data))
        self.assertIn(quote(name, safe=''), response.headers['content-disposition'])

    def test_missing_and_removed_documents_are_not_served(self):
        self.assertEqual(self.client.get('/documents/missing.pdf/file').status_code, 404)
        self.upload()
        self.client.delete('/documents', params={'filename': 'guide.pdf'})
        self.assertEqual(self.client.get('/documents/guide.pdf/file').status_code, 404)
        trash = next((self.directory / '.trash').glob('*/guide.pdf'))
        url = '/documents/' + quote(str(trash.relative_to(self.directory)), safe='') + '/file'
        self.assertEqual(self.client.get(url).status_code, 400)

    def test_path_traversal_and_symlinks_are_rejected(self):
        for name in ('../secret.pdf', '../../secret.env', '/etc/passwd', '..\\secret.pdf', '.env', 'guide.pdf\x00'):
            response = self.client.get('/documents/' + quote(name, safe='') + '/file')
            self.assertIn(response.status_code, (400, 404))
        outside = self.directory.parent / (self.directory.name + '-outside.pdf')
        outside.write_bytes(pdf_bytes('This must not leak'))
        self.addCleanup(outside.unlink)
        (self.directory / 'link.pdf').symlink_to(outside)
        response = self.client.get('/documents/link.pdf/file')
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(b'This must not leak', response.content)

    def test_symlink_swap_after_validation_cannot_escape(self):
        self.upload()
        original_open = os.open
        def swap(path, flags, *args, **kwargs):
            if str(path).endswith('guide.pdf'):
                path.unlink()
                path.symlink_to(self.directory / '.api.lock')
            return original_open(path, flags, *args, **kwargs)
        with patch('app.api.os.open', side_effect=swap):
            response = self.client.get('/documents/guide.pdf/file')
        self.assertEqual(response.status_code, 400)

    def test_non_pdf_and_size_limit(self):
        (self.directory / 'invalid.pdf').write_bytes(b'not pdf')
        self.assertEqual(self.client.get('/documents/invalid.pdf/file').status_code, 422)
        self.upload()
        with patch('app.api.MAX_PDF_BYTES', 10):
            self.assertEqual(self.client.get('/documents/guide.pdf/file').status_code, 413)
