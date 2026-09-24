import io
from pathlib import Path
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from app.api import create_app
from app.ingest import load_and_chunk_pdfs


def pdf_bytes(text='A document about retrieval.'):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(f'BT /F1 12 Tf 20 200 Td ({text}) Tj ET'.encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO(); writer.write(output)
    return output.getvalue()


class FakeIndex:
    def __init__(self, directory):
        self.chunks = load_and_chunk_pdfs(directory)
        self.closed = False

    def retrieve(self, question, allowed, top_k=4):
        assert not self.closed
        return [(chunk['text'], {'source': chunk['source'], 'page': chunk['page'], 'chunk_id': f'chunk-{i}',
                                 'index_id': 'test-index', 'distance': float(i) / 10, 'similarity_score': 1.0 - i / 10})
                for i, chunk in enumerate(self.chunks) if chunk['source'] in allowed][:top_k]

    def close(self):
        self.closed = True


async def generate(question, chunks):
    return 'Grounded answer'


class ApiFixture:
    def setup_api(self, **kwargs):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        env = patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
        env.start(); self.addCleanup(env.stop)
        kwargs.setdefault('builder', FakeIndex)
        kwargs.setdefault('generator', generate)
        self.app = create_app(self.directory, poll_seconds=0.02, **kwargs)
        self.service = self.app.state.index
        self.client = self.enterContext(TestClient(self.app))

    def upload(self, name='guide.pdf', data=None):
        return self.client.post('/documents', files={'file': (name, pdf_bytes() if data is None else data, 'application/pdf')})

    def ready(self):
        with self.service.condition:
            target = self.service.signature()
            assert self.service.condition.wait_for(
                lambda: self.service.current is not None and self.service.current.signature == target,
                timeout=5,
            ), 'Index did not become ready'
