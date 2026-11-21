"""Bounded parser subprocess. A process limit is not a full malware sandbox."""

import json
import resource
import sys

resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))

import fitz
from packages.pdf import inspect_pdf

path = sys.argv[1]
with fitz.open(path) as doc:
    if doc.xref_length() > 50000:
        raise ValueError("Too many PDF objects.")
    for i in range(1, doc.xref_length()):
        obj = doc.xref_object(i)
        if any(
            token in obj
            for token in (
                "/JavaScript",
                "/Launch",
                "/EmbeddedFiles",
                "/RichMedia",
                "/OpenAction",
                "/JS ",
                "/XFA",
            )
        ):
            raise ValueError("Active content is not accepted.")
print(json.dumps(inspect_pdf(path)))
