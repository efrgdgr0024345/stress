"""Exercise the exact deployment ZIP under a 1 GiB container memory limit."""
import argparse
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
HARNESS="""import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('caesar_function','/function/__main__.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
print(json.dumps(module.main(json.load(sys.stdin))))
"""


def invoke(function,event):
    command=['docker','run','--rm','-i','--network=none','--memory=1g','--memory-swap=1g','--cpus=1','--pids-limit=32','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--user',f'{os.getuid()}:{os.getgid()}','--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=128m','--mount',f'type=bind,src={function},dst=/function,readonly','--workdir=/function','python:3.12-slim','python','-I','-c',HARNESS]
    started=time.monotonic()
    result=subprocess.run(command,input=json.dumps(event).encode(),capture_output=True,timeout=240)
    if result.returncode:raise RuntimeError('Function container failed: '+result.stderr.decode(errors='replace')[-1500:])
    if len(result.stdout)>1000000:raise ValueError('Function response exceeds provider limit')
    return json.loads(result.stdout)['body'],time.monotonic()-started,len(result.stdout)


def qualify(build,report_path):
    import sys
    sys.path.insert(0,str(ROOT))
    from packages.automation.contracts import PageEvidence
    from packages.automation.recognize import materials
    source=(ROOT/'fixtures/1010/1010 Reviewed.pdf').read_bytes();digest=hashlib.sha256(source).hexdigest()
    event={'pdf_base64':base64.b64encode(source).decode(),'sha256':digest,'page':0}
    if len(json.dumps(event).encode())>1000000:raise ValueError('Fixture input exceeds provider limit')
    report={'format':'caesar-functions-qualification-1','build':json.loads((build/'build-report.json').read_text()),'limits':{'memory_mib':1024,'cpus':1,'network':'none','swap':False},'source_sha256':digest,'request_bytes':len(json.dumps(event).encode()),'pages':[],'digitalocean_live_tested':False,'engineering_verified':False}
    with tempfile.TemporaryDirectory(prefix='caesar-function-test-',dir=ROOT/'.local') as tmp:
        function=Path(tmp).resolve()
        with zipfile.ZipFile(build/'extract.zip') as archive:archive.extractall(function)
        for page in range(2):
            event['page']=page;value,elapsed,size=invoke(function,event)
            if not value.get('ok'):raise ValueError('Function failed: '+str(value.get('error')))
            evidence=json.loads(gzip.decompress(base64.b64decode(value['evidence'])))
            # This is where the website would validate worker data before use.
            evidence['isolation']='container-no-network';PageEvidence.model_validate(evidence)
            if evidence['source_sha256']!=digest or evidence['page_index']!=page or not evidence['ocr_used']:raise ValueError('Fixture OCR/evidence verification failed')
            sheet={'id':f'qualification-page-{page}','page_index':page,'line_id':'8-PG-JE3LN2-1010-FUTURE','width':evidence['width'],'height':evidence['height']}
            proposed,issues,ledger=materials(evidence,sheet,digest)
            if not proposed:raise ValueError('Real fixture produced no material proposals')
            if len(evidence.get('symbols',[]))!=(4,9)[page]:raise ValueError('Real fixture flange-location baseline changed; inspect source geometry before changing expectations.')
            result={'page':page+1,'words':len(evidence['words']),'material_proposals':len(proposed),'flange_location_proposals':len(evidence['symbols']),'response_bytes':size,'handler_elapsed_ms':value['elapsed_ms'],'wall_seconds':round(elapsed,3),'parser_peak_rss_kib':value['parser_peak_rss_kib'],'low_confidence_words':len(evidence.get('uncertain_words',[]))}
            report['pages'].append(result);print(json.dumps(result),flush=True)
        bad=dict(event,sha256='0'*64);value,_,_=invoke(function,bad)
        if value.get('error')!='SOURCE_HASH_MISMATCH':raise ValueError('Hash mismatch not rejected')
        bad=dict(event,url='https://example.invalid');value,_,_=invoke(function,bad)
        if value.get('error')!='INVALID_INPUT':raise ValueError('Arbitrary URL not rejected')
        import fitz
        active=fitz.open();active.new_page();action=active.get_new_xref();active.update_object(action,'<< /S /JavaScript /JS (app.alert(1)) >>');active.xref_set_key(active.pdf_catalog(),'OpenAction',f'{action} 0 R');raw=active.tobytes();active.close()
        value,_,_=invoke(function,{'pdf_base64':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest(),'page':0})
        if value.get('ok') or value.get('error')!='PROCESSING_FAILED':raise ValueError('Active PDF not rejected')
    report['material_proposals']=sum(p['material_proposals'] for p in report['pages'])
    if report['material_proposals']!=32:raise ValueError('Frozen extraction profile changed its 32 proposal software baseline; inspect before updating expectations.')
    report['passed']=True;report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: deployment ZIP, two real OCR pages, evidence contracts, hash/URL rejection and 1 GiB container profile.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('build',type=Path);parser.add_argument('--report',type=Path,default=ROOT/'.local/functions-qualification.json');args=parser.parse_args();qualify(args.build.resolve(),args.report.resolve())
