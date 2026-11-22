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
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.error import HTTPError, URLError

ROOT=Path(__file__).resolve().parent
MAX_PDF=700000
MAX_FRAME=1000000
MAX_PAGE=30*1024**2
MAX_EVIDENCE=16*1024**2


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def remote_input(event):
    required={'source_url','result_url','lease','request_id','sha256','page'}
    if set(event)!=required or event.get('page')!=0:return False
    identity=event.get('request_id');lease=event.get('lease')
    if not isinstance(identity,str) or not re.fullmatch(r'[a-f0-9-]{36}',identity):return False
    if not isinstance(lease,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',lease):return False
    prefix='https://easyai.com.au/stress/api/v1/worker/pages/'+identity
    return event.get('source_url')==prefix+'/source' and event.get('result_url')==prefix+'/result'


def transfer(event,activation,body=None):
    headers={'Authorization':'Bearer '+event['lease'],'X-Caesar-Activation':activation,
             'User-Agent':'CAESAR-page-worker','Content-Type':'application/gzip'}
    req=Request(event['source_url'] if body is None else event['result_url'],
                data=body,headers=headers,method='GET' if body is None else 'POST')
    with build_opener(NoRedirect()).open(req,timeout=20) as response:
        if body is not None:
            if not 200<=response.status<300:raise ValueError('RESULT_DELIVERY_FAILED')
            return None
        content=response.read(MAX_PAGE+1)
        if len(content)>MAX_PAGE:raise ValueError('PAGE_TRANSFER_LIMIT')
        return content


def failure(code):return {'body':{'format':'caesar-function-result-1','ok':False,'error':code}}


def main(event,context=None):
    if not isinstance(event,dict):return failure('INVALID_INPUT')
    remote='source_url' in event
    if remote and not remote_input(event):return failure('INVALID_TRANSFER_INPUT')
    if not remote and set(event)-{'pdf_base64','sha256','page'}:return failure('INVALID_INPUT')
    encoded=event.get('pdf_base64');digest=event.get('sha256');page=event.get('page')
    if (not remote and (not isinstance(encoded,str) or len(encoded)>((MAX_PDF+2)//3)*4)) or not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest) or type(page) is not int or not 0<=page<100:return failure('INVALID_INPUT')
    if len(json.dumps(event).encode())>MAX_FRAME:return failure('INPUT_LIMIT')
    if context is not None and callable(getattr(context,'get_remaining_time_in_millis',None)) and context.get_remaining_time_in_millis()<5000:return failure('DEADLINE_EXCEEDED')
    activation=os.environ.get('__OW_ACTIVATION_ID','')
    if not activation and context is not None:
        activation=context.get('activation_id','') if isinstance(context,dict) else getattr(context,'activation_id','')
        if not activation and callable(getattr(context,'get_activation_id',None)):activation=context.get_activation_id()
    if remote and not re.fullmatch(r'[a-f0-9]{32}',activation):return failure('ACTIVATION_CONTEXT_UNAVAILABLE')
    started=time.monotonic()
    try:pdf=transfer(event,activation) if remote else base64.b64decode(encoded,validate=True)
    except (HTTPError,URLError,TimeoutError,OSError):return failure('SOURCE_TRANSFER_FAILED')
    except (ValueError,binascii.Error):return failure('PAGE_TRANSFER_FAILED' if remote else 'INVALID_BASE64')
    if len(pdf)>(MAX_PAGE if remote else MAX_PDF) or not pdf.startswith(b'%PDF-'):return failure('INVALID_PDF')
    if hashlib.sha256(pdf).hexdigest()!=digest:return failure('SOURCE_HASH_MISMATCH')
    timeout=210
    if remote:timeout=min(180,195-(time.monotonic()-started))
    if context is not None and callable(getattr(context,'get_remaining_time_in_millis',None)):
        timeout=min(timeout,(context.get_remaining_time_in_millis()-5000)/1000)
    if timeout<1:return failure('DEADLINE_EXCEEDED')
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
    if remote:
        delivered={'format':'caesar-remote-page-result-1','request_id':event['request_id'],
                   'evidence':evidence,'elapsed_ms':result['elapsed_ms'],
                   'parser_peak_rss_kib':result['parser_peak_rss_kib']}
        content=json.dumps(delivered,separators=(',',':')).encode()
        if len(content)>MAX_EVIDENCE:return failure('RESULT_LIMIT')
        body=gzip.compress(content,mtime=0)
        for attempt in range(2):
            try:
                transfer(event,activation,body)
                return {'body':{'format':'caesar-function-result-1','ok':True,'delivery':'callback',
                                'request_id':event['request_id'],'elapsed_ms':result['elapsed_ms'],
                                'parser_peak_rss_kib':result['parser_peak_rss_kib']}}
            except (HTTPError,URLError,TimeoutError,OSError,ValueError):pass
        # A small normal result can still be recovered from the activation log.
        result['request_id']=event['request_id']
    frame={'body':result}
    if len(json.dumps(frame).encode())>MAX_FRAME:return failure('RESULT_LIMIT')
    return frame
