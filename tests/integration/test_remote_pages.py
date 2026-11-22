"""Normal upload → scoped page transfers → incremental review → native draft.

The provider boundary is fake; parsing, application routes, transactions, exports
and byte/hash identity checks are real. No external account or billable call.
"""
import base64
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch
import zipfile
import fitz
from fastapi.testclient import TestClient
from packages.pdf import inspect_pdf, content_hash
from packages.automation.extract import extract_page
from services.api import main, pipeline, remote_pages as remote, remote_setup
from services.api.updates import write
from tests.integration import test_api as fixtures
from tests.integration.test_pipeline import drawing


def executor(path, mode, page=0, **kwargs):
    if mode == 'register':return inspect_pdf(path)
    if mode != 'slice':raise AssertionError('Heavy OCR must use the provider')
    with fitz.open(path) as source, fitz.open() as single:
        original = source[page]
        metadata = {'width': original.cropbox.width, 'height': original.cropbox.height,
                    'rotation': original.rotation, 'content_hash': content_hash(original)}
        single.insert_pdf(source, from_page=page, to_page=page, links=False, annots=True)
        content = single.tobytes(garbage=4, deflate=True)
    return {'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(), 'page_index':page,
            'metadata':metadata, 'page_sha256':hashlib.sha256(content).hexdigest(),
            'pdf_base64':base64.b64encode(content).decode()}


class FakeProvider:
    def __init__(self, case):
        self.case=case;self.calls=[];self.jobs=[];self.bare=TestClient(main.app)
    def call(self, api, path, method='GET', body=None, pending=False):
        if method=='POST':
            self.calls.append(deepcopy(body))
            identity=f'{len(self.calls):032x}'
            headers={'Authorization':'Bearer '+body['lease'],'X-Caesar-Activation':identity}
            response=self.bare.get(body['source_url'].replace('https://easyai.com.au/stress',''),headers=headers)
            self.case.assertEqual(response.status_code,200,response.text[:100])
            self.case.assertEqual(hashlib.sha256(response.content).hexdigest(),body['sha256'])
            with fitz.open(stream=response.content,filetype='pdf') as doc:self.case.assertEqual(len(doc),1)
            self.jobs.append({'event':deepcopy(body),'activation':identity,'headers':headers,'content':response.content,'result':None})
            return {'activationId':identity}
        identity=path.rsplit('/',1)[-1]
        job=next(j for j in self.jobs if j['activation']==identity)
        return job['result']
    def value(self,index):
        job=self.jobs[index]
        path=Path(self.case.temp.name)/f'provider-{index}.pdf';path.write_bytes(job['content'])
        evidence=extract_page(path,0,ocr=False)
        return {'format':'caesar-remote-page-result-1','request_id':job['event']['request_id'],
                'evidence':evidence,'elapsed_ms':123,'parser_peak_rss_kib':123456}
    def finish(self,index, value=None):
        job=self.jobs[index];value=value or self.value(index)
        packed=gzip.compress(json.dumps(value).encode())
        response=self.bare.post(job['event']['result_url'].replace('https://easyai.com.au/stress',''),
            content=packed,headers={**job['headers'],'Content-Type':'application/gzip'})
        return response


class RemotePagesTests(unittest.TestCase):
    setUp_base=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    def setUp(self):
        self.setUp_base()
        write(remote_setup.directory(main.DATA)/'policy.json',{'enabled':True})
        write(remote_setup.directory(main.DATA)/'state.json',{'state':'ready','stage':'complete','code_sha256':remote_setup.version(main)})
        self.provider=FakeProvider(self)
    def intake(self,p,content=None):
        content=content or drawing()
        response=self.client.post(f"/api/v1/projects/{p['id']}/intake?version={p['version']}",content=content,headers={'Content-Type':'application/pdf','X-Filename':'drawing-pack.pdf'})
        self.assertEqual(response.status_code,202,response.text)
        self.__dict__.setdefault('inputs',{})[response.json()['id']]=content
        return response.json()
    def tick(self):
        with patch.object(pipeline,'execute',side_effect=executor),patch.object(remote,'execute',side_effect=executor),patch.object(remote_setup,'call',side_effect=self.provider.call):
            return pipeline.process_one(main)
    def wake(self):
        with main.db() as c:c.execute("UPDATE pipeline_runs SET next_at=0 WHERE state NOT IN ('DONE','FAILED','CANCELLED','SUPERSEDED')")
    def job(self,identity):
        with main.db() as c:return dict(c.execute('SELECT * FROM pipeline_runs WHERE id=?',(identity,)).fetchone())
    def project(self,p):return self.client.get(f"/api/v1/projects/{p['id']}").json()
    def started(self):
        p=self.create();job=self.intake(p)
        self.assertTrue(self.tick());self.assertTrue(self.tick())
        self.assertEqual(len(self.provider.calls),2)
        return p,job

    def test_out_of_order_pages_allow_early_review_and_finish_one_unchanged_project(self):
        p,job=self.started()
        self.assertTrue(all(set(e)=={'source_url','result_url','lease','request_id','sha256','page'} for e in self.provider.calls))
        self.assertTrue(all(e['page']==0 for e in self.provider.calls))
        self.assertEqual(self.provider.finish(1).status_code,200)
        self.wake();self.tick()
        early=self.project(p)
        self.assertTrue(early['materials'])
        self.assertTrue(early['automation']['partial_pages'])
        self.assertEqual(self.job(job['id'])['stage'],'extract')
        self.assertEqual(json.loads(self.job(job['id'])['progress'])['remote_pages_done'],[1])
        # A human can annotate a registered original while later work continues.
        response=self.client.post(f"/api/v1/projects/{p['id']}/annotations",json={
            'version':early['version'],'sheet_id':early['sheets'][1]['id'],'kind':'FreeText',
            'rect':[20,20,150,55],'text':'Human review during processing','color':'#cc4444'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.provider.finish(0).status_code,200)
        for _ in range(8):
            self.wake();self.tick()
            if self.job(job['id'])['state']=='DONE':break
        self.assertEqual(self.job(job['id'])['state'],'DONE',self.job(job['id']))
        final=self.project(p)
        self.assertEqual(len(final['sheets']),2)
        self.assertEqual(final['annotations'][0]['text'],'Human review during processing')
        self.assertEqual(len(self.provider.calls),2)
        expected=hashlib.sha256(self.inputs[job['id']]).hexdigest()
        self.assertTrue(all(v['sha256']==expected for v in final['sheets']))
        self.assertEqual(hashlib.sha256((main.DATA/'sources'/f"{self.job(job['id'])['source_id']}.pdf").read_bytes()).hexdigest(),expected)
        with main.db() as c:
            usage=c.execute("SELECT count FROM remote_usage WHERE bucket LIKE 'month:%'").fetchone()[0]
            artifact=c.execute('SELECT * FROM artifacts WHERE project_id=?',(p['id'],)).fetchone()
        self.assertEqual(usage,2)
        self.assertTrue(artifact)
        with zipfile.ZipFile(main.DATA/'exports'/f"{artifact['id']}.zip") as z:self.assertIn('engineering-workbook.xlsx',z.namelist())
        for task in remote.rows(main,job['id']):
            self.assertEqual(task['state'],'DONE')
            self.assertFalse(remote.paths(main,task['id'])[0].exists())
            evidence=json.loads(pipeline.page_path(main,job['id'],task['page_index']).read_text())
            self.assertEqual(evidence['source_sha256'],task['source_sha'])
            self.assertEqual(evidence['page_index'],task['page_index'])

    def test_grants_are_scoped_expiring_single_activation_and_idempotent_for_results(self):
        p,job=self.started();one,two=self.provider.jobs
        url=one['event']['source_url'].replace('https://easyai.com.au/stress','')
        self.assertEqual(self.provider.bare.get(url).status_code,401)
        wrong={**one['headers'],'X-Caesar-Activation':'f'*32}
        self.assertEqual(self.provider.bare.get(url,headers=wrong).status_code,409)
        self.assertEqual(self.provider.bare.get(two['event']['source_url'].replace('https://easyai.com.au/stress',''),headers=one['headers']).status_code,401)
        bad=self.provider.value(0);bad['evidence']['source_sha256']='0'*64
        self.assertEqual(self.provider.finish(0,bad).status_code,422)
        good=self.provider.value(0)
        self.assertEqual(self.provider.finish(0,good).status_code,200)
        duplicate=self.provider.finish(0,good)
        self.assertEqual(duplicate.status_code,200)
        self.assertTrue(duplicate.json()['duplicate'])
        with main.db() as c:c.execute('UPDATE remote_pages SET expires=0 WHERE id=?',(two['event']['request_id'],))
        self.assertEqual(self.provider.finish(1).status_code,410)
        logs=self.client.get('/api/v1/system/logs/export').text
        public=self.client.get(f"/api/v1/projects/{p['id']}/pipeline").text
        for event in self.provider.calls:
            self.assertNotIn(event['lease'],logs+public)

    def test_cancelled_work_cannot_deliver_or_publish(self):
        p,job=self.started()
        self.assertEqual(self.client.post(f"/api/v1/projects/{p['id']}/pipeline/{job['id']}/cancel").status_code,200)
        self.assertEqual(self.provider.finish(0).status_code,410)
        self.assertFalse(self.tick())
        self.assertFalse(self.project(p)['materials'])
        self.assertEqual(self.job(job['id'])['state'],'CANCELLED')

    def test_result_geometry_schema_and_expansion_caps_are_enforced(self):
        p,job=self.started();one=self.provider.jobs[0]
        bad=self.provider.value(0);bad['evidence']['width']+=1
        self.assertEqual(self.provider.finish(0,bad).status_code,422)
        bad=self.provider.value(0);bad['command']='untrusted'
        self.assertEqual(self.provider.finish(0,bad).status_code,422)
        url=one['event']['result_url'].replace('https://easyai.com.au/stress','')
        packed=gzip.compress(b'A'*(remote.MAX_RESULT+1))
        self.assertEqual(self.provider.bare.post(url,content=packed,headers={**one['headers'],'Content-Type':'application/gzip'}).status_code,422)
        self.assertEqual(remote.rows(main,job['id'])[0]['state'],'SUBMITTED')

    def test_retry_reuses_completed_page_and_only_resubmits_the_failed_page(self):
        p,job=self.started()
        self.assertEqual(self.provider.finish(0).status_code,200)
        self.provider.jobs[1]['result']={'response':{'result':{'body':{'format':'caesar-function-result-1','ok':False,'error':'PROCESSING_FAILED'}}}}
        self.wake();self.tick();self.wake();self.tick()
        self.assertEqual(self.job(job['id'])['state'],'FAILED')
        response=self.client.post(f"/api/v1/projects/{p['id']}/pipeline/{job['id']}/retry")
        self.assertEqual(response.status_code,200,response.text)
        self.tick()
        self.assertEqual(len(self.provider.calls),3)
        self.assertEqual(self.provider.calls[2]['request_id'],self.provider.calls[1]['request_id'])
        self.assertNotEqual(self.provider.calls[2]['lease'],self.provider.calls[1]['lease'])
        self.assertEqual(self.provider.finish(2).status_code,200)
        for _ in range(6):
            self.wake();self.tick()
            if self.job(job['id'])['state']=='DONE':break
        self.assertEqual(self.job(job['id'])['state'],'DONE')
        self.assertEqual(len(self.provider.calls),3)

    def test_global_concurrency_and_monthly_budget_cover_multiple_projects(self):
        p,job=self.started()
        other=self.create();second=self.intake(other)
        self.tick();self.tick()
        self.assertEqual(len(self.provider.calls),2)
        self.assertEqual(self.job(second['id'])['stage'],'extract')
        write(remote_setup.directory(main.DATA)/'policy.json',{'enabled':True,'monthly_limit':2})
        for i in (0,1):self.assertEqual(self.provider.finish(i).status_code,200)
        self.wake()
        for _ in range(5):self.tick()
        self.assertEqual(len(self.provider.calls),2)
        progress=json.loads(self.job(second['id'])['progress'])
        self.assertEqual(progress['remote_wait'],'budget')
        self.assertGreater(self.job(second['id'])['next_at'],time.time())
