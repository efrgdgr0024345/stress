"""Private DigitalOcean Functions demo: one inline PDF, one extraction page.

This deliberately bounded interface is not the website's production transport.
No account credentials, URLs, output paths or shell commands are accepted.
"""
import base64
import binascii
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parent
MAX_PDF=700000
MAX_FRAME=1000000


def failure(code):return {'body':{'format':'caesar-function-result-1','ok':False,'error':code}}


def main(event,context=None):
    if not isinstance(event,dict) or set(event)-{'pdf_base64','sha256','page'}:return failure('INVALID_INPUT')
    encoded=event.get('pdf_base64');digest=event.get('sha256');page=event.get('page')
    if not isinstance(encoded,str) or len(encoded)>((MAX_PDF+2)//3)*4 or not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest) or type(page) is not int or not 0<=page<100:return failure('INVALID_INPUT')
    if len(json.dumps(event).encode())>MAX_FRAME:return failure('INPUT_LIMIT')
    try:pdf=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error):return failure('INVALID_BASE64')
    if len(pdf)>MAX_PDF or not pdf.startswith(b'%PDF-'):return failure('INVALID_PDF')
    if hashlib.sha256(pdf).hexdigest()!=digest:return failure('SOURCE_HASH_MISMATCH')
    timeout=210
    if context is not None and callable(getattr(context,'get_remaining_time_in_millis',None)):
        timeout=min(timeout,(context.get_remaining_time_in_millis()-5000)/1000)
    if timeout<1:return failure('DEADLINE_EXCEEDED')
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='caesar-function-') as temporary:
        work=Path(temporary);source=work/'input.pdf';source.write_bytes(pdf)
        environment={'PATH':'/no-external-tools','TMPDIR':str(work),'OMP_THREAD_LIMIT':'1','PYTHONDONTWRITEBYTECODE':'1'}
        try:
            with (work/'stderr').open('wb') as errors:
                done=subprocess.run([sys.executable,'-I',str(ROOT/'worker_child.py'),str(source),str(page)],cwd=work,env=environment,stdout=subprocess.DEVNULL,stderr=errors,timeout=timeout)
            output=work/'result.json'
            if done.returncode or not output.is_file() or output.is_symlink() or output.stat().st_size>16*1024**2:return failure('PROCESSING_FAILED')
            value=json.loads(output.read_text())
        except subprocess.TimeoutExpired:return failure('PROCESSING_TIMEOUT')
        except (OSError,ValueError):return failure('INVALID_WORKER_RESULT')
    evidence=value['evidence']
    if evidence.get('source_sha256')!=digest or evidence.get('page_index')!=page:return failure('EVIDENCE_IDENTITY_MISMATCH')
    packed=base64.b64encode(gzip.compress(json.dumps(evidence,separators=(',',':')).encode(),mtime=0)).decode()
    result={'format':'caesar-function-result-1','ok':True,'encoding':'gzip+base64','source_sha256':digest,'page':page,'evidence':packed,'elapsed_ms':round((time.monotonic()-started)*1000),'parser_peak_rss_kib':value['parser_peak_rss_kib']}
    frame={'body':result}
    if len(json.dumps(frame).encode())>MAX_FRAME:return failure('RESULT_LIMIT')
    return frame
