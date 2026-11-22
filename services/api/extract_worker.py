"""Run in a dedicated disposable directory with a sanitized environment."""
import json
import os
from pathlib import Path
import resource
import sys

resource.setrlimit(resource.RLIMIT_CPU, (160, 160))
resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024**2, 1536 * 1024**2))
resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2, 64 * 1024**2))
os.umask(0o077)
from services.api.parser_sandbox import restrict
if os.environ.get("CAESAR_SANDBOX_CONTAINER") != "1" and os.environ.get("CAESAR_BOUNDED_PILOT") != "1":
    restrict(Path.cwd(), Path(__file__).resolve().parents[2])
from packages.automation.extract import extract_page

if sys.argv[3] == 'slice':
    import base64, hashlib, fitz
    from packages.pdf import content_hash
    with fitz.open(sys.argv[1]) as source:
        index = int(sys.argv[2])
        if not 1 <= len(source) <= 100 or not 0 <= index < len(source):
            raise ValueError('PDF_PAGE_LIMIT')
        page = source[index]
        metadata = {'width': page.cropbox.width, 'height': page.cropbox.height,
                    'rotation': page.rotation, 'content_hash': content_hash(page)}
        with fitz.open() as single:
            single.insert_pdf(source, from_page=index, to_page=index, links=False, annots=True)
            if content_hash(single[0]) != metadata['content_hash']:
                raise ValueError('SPLIT_CONTENT_CHANGED')
            content = single.tobytes(garbage=4, deflate=True, no_new_id=True)
    if len(content) > 30 * 1024**2:
        result = {'error': 'PAGE_TRANSFER_LIMIT'}
    else:
        result = {'page_index': index, 'source_sha256': hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest(),
                  'page_sha256': hashlib.sha256(content).hexdigest(), 'pdf_base64': base64.b64encode(content).decode(),
                  'metadata': metadata}
elif sys.argv[3] == "register":
    import fitz
    from packages.pdf import inspect_pdf
    with fitz.open(sys.argv[1]) as document:
        if document.xref_length() > 50000:
            raise ValueError("PDF_OBJECT_LIMIT")
        for i in range(1, document.xref_length()):
            if any(s in document.xref_object(i) for s in ("/JavaScript", "/Launch", "/EmbeddedFiles", "/RichMedia", "/OpenAction", "/JS ", "/XFA")):
                raise ValueError("ACTIVE_CONTENT_REJECTED")
    result = inspect_pdf(sys.argv[1])
else:
    result = extract_page(Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3] == "ocr")
Path(sys.argv[4]).write_text(json.dumps(result))
