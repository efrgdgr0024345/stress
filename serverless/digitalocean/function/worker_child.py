"""Disposable parser subprocess; the handler's environment is not inherited."""
import json
import os
from pathlib import Path
import resource
import sys

resource.setrlimit(resource.RLIMIT_CPU,(180,180))
resource.setrlimit(resource.RLIMIT_AS,(1536*1024**2,1536*1024**2))
resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
os.umask(0o077)
root=Path(__file__).resolve().parent
sys.path[:0]=[str(root),str(root/'lib')]
os.environ['CAESAR_OCR_HOME']=str(root/'ocr')
import fitz
with fitz.open(sys.argv[1]) as doc:
    if not 1<=len(doc)<=100 or not 0<=int(sys.argv[2])<len(doc) or doc.xref_length()>50000:raise ValueError('DOCUMENT_LIMIT')
    for index in range(1,doc.xref_length()):
        if any(s in doc.xref_object(index) for s in ('/JavaScript','/Launch','/EmbeddedFiles','/RichMedia','/OpenAction','/JS ','/XFA')):raise ValueError('ACTIVE_CONTENT')
from packages.automation.extract import extract_page
evidence=extract_page(Path(sys.argv[1]),int(sys.argv[2]))
Path('result.json').write_text(json.dumps({'evidence':evidence,'parser_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))
