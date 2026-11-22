"""Deploy and smoke-test only the private Functions demo; no VPS is created.

Requires DIGITALOCEAN_ACCESS_TOKEN through the execution environment, never
command arguments. Provider credentials/output are never written to reports.
"""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
API='https://api.digitalocean.com/v2/functions/namespaces'


def api(token,method='GET',body=None,path=''):
    request=Request(API+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urlopen(request,timeout=30) as response:return json.load(response)
    except HTTPError as error:raise RuntimeError(f'DigitalOcean Functions API returned HTTP {error.code}.') from None


def cli(arguments):
    done=subprocess.run(['doctl','serverless',*arguments],capture_output=True,text=True,timeout=360)
    if done.returncode:raise RuntimeError('DigitalOcean CLI failed during '+arguments[0]+'. Credentials and raw output were withheld from logs.')
    return done.stdout


def find_result(value):
    if isinstance(value,dict):
        if value.get('format')=='caesar-function-result-1':return value
        for key in ('body','result','response'):
            if key in value:
                found=find_result(value[key])
                if found:return found
    return None


def deploy(build,region,report):
    token=os.environ.get('DIGITALOCEAN_ACCESS_TOKEN','')
    if not token:raise RuntimeError('Set the DIGITALOCEAN_ACCESS_TOKEN GitHub Actions secret or a secure environment binding; no provider requests were made.')
    qualification=json.loads((build/'qualification.json').read_text())
    if not qualification.get('passed'):raise ValueError('Local function qualification must pass before deployment.')
    package=build/'deploy/packages/caesar/extract/extract.zip'
    if hashlib.sha256(package.read_bytes()).hexdigest()!=qualification['build']['zip_sha256']:raise ValueError('Deployment artifact differs from the qualified ZIP.')
    from services.api.digitalocean import namespaces
    available=namespaces(api(token))
    matches=[n for n in available if n.get('label')=='caesar-functions-demo' and n.get('region')==region]
    if len(matches)>1:raise RuntimeError('More than one demo namespace matches; no namespace changed.')
    if matches:namespace=api(token,path='/'+matches[0]['namespace'])['namespace']
    else:namespace=api(token,'POST',{'region':region,'label':'caesar-functions-demo'})['namespace']
    namespace_id=namespace['namespace']
    cli(['install']);cli(['connect',namespace_id]);cli(['deploy',str(build/'deploy'),'--include','caesar/extract'])
    source=(ROOT/'fixtures/1010/1010 Reviewed.pdf').read_bytes();digest=hashlib.sha256(source).hexdigest()
    evidence_report={'format':'caesar-functions-live-demo-1','namespace_id':namespace_id,'region':region,'function':'caesar/extract','web_access':False,'source_sha256':digest,'digitalocean_live_tested':True,'engineering_verified':False,'pages':[]}
    from packages.automation.contracts import PageEvidence
    from packages.automation.recognize import materials
    with tempfile.TemporaryDirectory(prefix='caesar-do-invoke-') as temporary:
        for index in range(2):
            event={'pdf_base64':base64.b64encode(source).decode(),'sha256':digest,'page':index}
            params=Path(temporary)/'input.json';params.write_text(json.dumps(event));params.chmod(0o600)
            result=find_result(json.loads(cli(['functions','invoke','caesar/extract','--full','--param-file',str(params)])))
            if not result or not result.get('ok'):raise RuntimeError('Live function did not return valid extraction evidence.')
            value=json.loads(gzip.decompress(base64.b64decode(result['evidence'])))
            # Provider Functions do not establish our local no-network Docker
            # profile. Record the provider boundary without inventing isolation.
            PageEvidence.model_validate({**value,'isolation':'provider-function'})
            if value['source_sha256']!=digest or value['page_index']!=index or not value['ocr_used']:raise ValueError('Live OCR identity/coverage failed.')
            sheet={'id':f'live-page-{index}','page_index':index,'line_id':'8-PG-JE3LN2-1010-FUTURE'}
            proposed,_,_=materials(value,sheet,digest)
            entry={'page':index+1,'words':len(value['words']),'material_proposals':len(proposed),'handler_elapsed_ms':result['elapsed_ms'],'parser_peak_rss_kib':result['parser_peak_rss_kib']}
            evidence_report['pages'].append(entry);print(json.dumps(entry),flush=True)
    evidence_report['passed']=True
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(evidence_report,indent=2)+'\n')
    print('Live DigitalOcean function demo passed. No Droplet, paid database, Spaces bucket or schedule was created.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('build',type=Path);parser.add_argument('--region',default='syd1',choices=['syd1','sgp1','nyc3','fra1']);parser.add_argument('--report',type=Path,default=ROOT/'.local/functions-live-demo.json');args=parser.parse_args()
    try:deploy(args.build.resolve(),args.region,args.report.resolve())
    except (RuntimeError,ValueError,KeyError,subprocess.TimeoutExpired) as error:raise SystemExit(str(error))
