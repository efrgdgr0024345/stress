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

if sys.argv[3] == "register":
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
