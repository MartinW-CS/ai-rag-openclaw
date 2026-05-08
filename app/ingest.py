"""PDF ingestion: load PDFs and split into chunks with source/page metadata."""
from pathlib import Path
from pypdf import PdfReader

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

def load_and_chunk_pdfs(data_dir: Path):
    """Read all PDFs in data_dir and return list of {text, source, page} chunks."""
    chunks = []
    for pdf_path in sorted(data_dir.glob("*.pdf")):
        reader = PdfReader(str(pdf_path))
        for page_num, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            i = 0
            while i < len(text):
                chunks.append({
                    "text": text[i : i + CHUNK_SIZE],
                    "source": pdf_path.name,
                    "page": page_num,
                })
                i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks