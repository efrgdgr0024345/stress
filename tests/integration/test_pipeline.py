"""End-to-end contracts, queue recovery and user corrections with disposable data."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import time
import asyncio
import unittest
from unittest.mock import patch
import zipfile

import fitz
from fastapi.testclient import TestClient
from packages.automation.extract import extract_page
from packages.automation.recognize import station_constraints
from packages.pdf import inspect_pdf,content_hash
from services.api import main,pipeline
from tests.integration import test_api as fixtures


def drawing(pages=2,label="AUTO-TEST-001"):
    doc=fitz.open()
    for i in range(pages):
        page=doc.new_page(width=1200,height=850)
        page.insert_text((60,40),f"{label} SHEET {i+1} OF {pages} REV A")
        for j in range(2):
            page.insert_text((100,180+j*100),f"POINT S{i*2+j+1} SUPPORT ROUTE main ORDER {i*2+j+1} STATION {(i*2+j)*50} mm",fontsize=10)
        for x,t in [(650,"ITEM"),(700,"DESCRIPTION"),(1000,"SIZE"),(1100,"QTY")]:page.insert_text((x,80),t)
        for x,t in [(650,"1"),(700,"FLANGE WN ASME B16.5 CLASS 150 RF"),(1000,"8"),(1100,"2")]:page.insert_text((x,110),t,fontsize=10)
        page.insert_text((60,800),"Synthetic explicit semantic source profile. Not a real drawing or engineering approval.",fontsize=9)
    result=doc.tobytes();doc.close();return result


def native_executor(path,mode,page=0,heartbeat=lambda:None):
    heartbeat()
    if mode=="register":return inspect_pdf(path)
    return {**extract_page(path,page,ocr=False),"isolation":"bounded-pilot"}


class PipelineTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown

    def create(self):return self.client.post('/api/v1/projects',json={"title":"Unattended pipeline regression","line_id":"AUTO-TEST-001"}).json()
    def intake(self,p,raw=None,replace=None):
        response=self.client.post(f"/api/v1/projects/{p['id']}/intake?version={p['version']}"+(f"&replace_source_id={replace}" if replace else ''),content=raw or drawing(),headers={"Content-Type":"application/pdf","X-Filename":"test.pdf"})
        self.assertEqual(response.status_code,202,response.text);return response.json()
    def current(self,p):return self.client.get(f"/api/v1/projects/{p['id']}").json()
    def drain(self,p):
        with patch.object(pipeline,'execute',side_effect=native_executor):
            for _ in range(40):
                if not pipeline.process_one(main):break
            else:self.fail('Pipeline did not stop at an idle state')
        return self.client.get(f"/api/v1/projects/{p['id']}/pipeline").json()['runs']

    def test_upload_to_native_draft_without_manual_items_or_nodes(self):
        p=self.create();original=drawing();job=self.intake(p,original)
        self.assertEqual(self.current(p)['sheets'],[])
        rows=self.drain(p);self.assertEqual(rows[0]['state'],'DONE',rows)
        p=self.current(p)
        self.assertEqual(len(p['sheets']),2);self.assertEqual(len(p['nodes']),4);self.assertEqual(len(p['materials']),2)
        self.assertEqual([n['proposed_station_mm'] for n in p['nodes']],['0','50','100','150'])
        self.assertTrue(all(n['station_mm'] is None for n in p['nodes']))
        self.assertTrue(all('SOURCE_PROPOSAL_REVIEW' in n['reasons'] for n in p['nodes']))
        self.assertIn('UNVERIFIED_DIMENSION',p['nodes'][1]['reasons'])
        artifact=rows[0]['progress']['artifact']
        response=self.client.get(f"/api/v1/projects/{p['id']}/artifacts/{artifact['id']}/download")
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            self.assertIn('automation-report.json',z.namelist())
            report=json.loads(z.read('automation-report.json'));self.assertEqual(report['coverage']['pages'],2)
            with fitz.open(stream=original,filetype='pdf') as before,fitz.open(stream=z.read('annotated-review.pdf'),filetype='pdf') as after:
                self.assertEqual(len(after),2)
                for i in range(2):self.assertEqual(content_hash(before[i]),content_hash(after[i]))
        again=self.client.post(f"/api/v1/projects/{p['id']}/exports",json={'version':p['version']})
        self.assertEqual(again.json()['id'],artifact['id'])

    def test_duplicate_input_creates_one_job_and_no_orphan_source(self):
        p=self.create();raw=drawing();a=self.intake(p,raw);b=self.intake(p,raw)
        self.assertEqual(a['id'],b['id'])
        with main.db() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM pipeline_runs').fetchone()[0],1)
        self.assertEqual(len(list((main.DATA/'sources').glob('*.pdf'))),2) # seed + quarantine

    def test_claims_serialize_project_and_expired_fence_is_rejected(self):
        p=self.create();self.intake(p);self.intake(p,drawing(label='SECOND'))
        a=pipeline.claim(main);self.assertIsNone(pipeline.claim(main))
        with main.db() as conn:conn.execute('UPDATE pipeline_runs SET lease=0 WHERE id=?',(a['id'],))
        b=pipeline.claim(main);self.assertEqual(a['id'],b['id']);self.assertGreater(b['fence'],a['fence'])
        with main.db() as conn:
            with self.assertRaisesRegex(RuntimeError,'STALE'):pipeline.fenced(conn,a)

    def test_cancelled_job_cannot_publish(self):
        p=self.create();job=self.intake(p);attempt=pipeline.claim(main)
        self.assertEqual(self.client.post(f"/api/v1/projects/{p['id']}/pipeline/{job['id']}/cancel").status_code,200)
        with patch.object(pipeline,'execute',side_effect=native_executor):
            with self.assertRaisesRegex(RuntimeError,'STALE'):pipeline.register(main,attempt,json.loads(attempt['progress']))
        self.assertEqual(self.current(p)['sheets'],[])

    def test_edits_and_deletions_survive_automatic_cached_refresh(self):
        p=self.create();self.intake(p);self.drain(p);p=self.current(p)
        node=p['nodes'][0];body=fixtures.ApiTests.node(self,p,'123 mm','Engineer-entered regression evidence')
        body.update(order=node['order'],kind=node['kind'],instances=deepcopy(node['instances']))
        body['instances'][0]['bubble']=[450,400]
        response=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{node['id']}",json=body)
        self.assertEqual(response.status_code,200,response.text);p=response.json()
        removed=p['nodes'][-1]['id']
        p=self.client.delete(f"/api/v1/projects/{p['id']}/nodes/{removed}?version={p['version']}").json()
        self.drain(p);p=self.current(p)
        saved=next(n for n in p['nodes'] if n['id']==node['id'])
        self.assertEqual(saved['station_mm'],'123');self.assertEqual(saved['instances'][0]['bubble'],[450,400])
        self.assertNotIn(removed,{n['id'] for n in p['nodes']})
        self.assertNotIn('SOURCE_PROPOSAL_REVIEW',saved['reasons'])

    def test_changed_revision_preserves_other_documents_and_archives_old_edits(self):
        p=self.create();raw=drawing();self.intake(p,raw);self.drain(p);p=self.current(p)
        original_source=p['sheets'][0]['source_id'];original_node=deepcopy(p['nodes'][0])
        self.intake(p,drawing(1,'OTHER'));self.drain(p);p=self.current(p)
        other_id=p['sheets'][-1]['id']
        self.intake(p,drawing(1,'CHANGED'),original_source);self.drain(p);p=self.current(p)
        self.assertEqual(len(p['sheets']),2);self.assertIn(other_id,{s['id'] for s in p['sheets']})
        self.assertTrue(all(s['source_id']!=original_source for s in p['sheets']))
        old=p['source_history'][0]
        self.assertEqual(old['nodes'][0]['instances'],original_node['instances'])
        response=self.client.get(f"/api/v1/projects/{p['id']}/sources/{original_source}")
        self.assertEqual(hashlib.sha256(response.content).digest(),hashlib.sha256(raw).digest())
        self.assertTrue(any(i['code']=='REVISION_REBASE_REQUIRED' for i in p['issues']))

    def test_reordered_unchanged_pages_keep_sheet_and_point_identities(self):
        p=self.create();raw=drawing();self.intake(p,raw);self.drain(p);p=self.current(p)
        old_ids={s['page_index']:s['id'] for s in p['sheets']};old_nodes={n['id'] for n in p['nodes']}
        source=p['sheets'][0]['source_id']
        with fitz.open(stream=raw,filetype='pdf') as original:
            output=fitz.open();output.insert_pdf(original,from_page=1,to_page=1);output.insert_pdf(original,from_page=0,to_page=0);changed=output.tobytes();output.close()
        self.intake(p,changed,source);self.drain(p);p=self.current(p)
        self.assertEqual(p['sheets'][0]['id'],old_ids[1]);self.assertEqual(p['sheets'][1]['id'],old_ids[0])
        self.assertEqual({n['id'] for n in p['nodes']},old_nodes)

    def test_queue_evidence_and_policy_authorization(self):
        p=self.create();job=self.intake(p)
        self.assertEqual(TestClient(main.app).post(f"/api/v1/projects/{p['id']}/intake?version=1",content=b'%PDF-').status_code,401)
        with main.db() as conn:conn.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertEqual(self.client.post(f"/api/v1/projects/{p['id']}/pipeline/{job['id']}/cancel").status_code,403)
        self.assertEqual(self.client.post('/api/v1/system/pipeline/config',json={'mode':'bounded_pilot'}).status_code,403)
        with main.db() as conn:conn.execute("UPDATE users SET role='admin',tenant='other' WHERE id='local-engineer'")
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}/pipeline/{job['id']}/evidence/0").status_code,404)

    def test_unknown_units_and_inconsistent_dimensions_stay_unknown(self):
        values,errors=station_constraints({'A':'0 mm','B':None,'C':None},[('A','B','2 in')])
        self.assertEqual(values['B'],'50.8');self.assertIsNone(values['C']);self.assertEqual(errors,[])
        values,errors=station_constraints({'A':'0 mm','B':'10 mm'},[('A','B','2 in')])
        self.assertTrue(errors);self.assertIsNone(values['A']);self.assertIsNone(values['B'])

    def test_unauthenticated_multipart_is_rejected_before_receive(self):
        received=[];messages=[]
        async def run():
            async def receive():received.append(True);raise AssertionError('Unauthorized request body was consumed')
            async def send(message):messages.append(message)
            await main.app({'type':'http','http_version':'1.1','method':'POST','scheme':'http','path':'/api/v1/catalogs/import','raw_path':b'/api/v1/catalogs/import','query_string':b'','root_path':'','server':('testserver',80),'client':('127.0.0.1',123),'headers':[(b'host',b'testserver'),(b'content-type',b'multipart/form-data; boundary=x'),(b'content-length',b'999999999')]},receive,send)
        asyncio.run(run());self.assertEqual(received,[])
        self.assertEqual(next(m for m in messages if m['type']=='http.response.start')['status'],401)

    def test_expired_registration_checkpoint_resumes_without_duplicate_pages(self):
        p=self.create();self.intake(p);attempt=pipeline.claim(main)
        with patch.object(pipeline,'execute',side_effect=native_executor),patch.object(pipeline,'advance',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):pipeline.register(main,attempt,json.loads(attempt['progress']))
        with main.db() as conn:conn.execute('UPDATE pipeline_runs SET lease=0 WHERE id=?',(attempt['id'],))
        self.assertEqual(self.drain(p)[0]['state'],'DONE')
        p=self.current(p);self.assertEqual(len(p['sheets']),2);self.assertEqual(len(p['nodes']),4)
        with main.db() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM sources WHERE project_id=?',(p['id'],)).fetchone()[0],1)

    def test_cancel_during_export_cannot_publish_an_artifact(self):
        p=self.create();job=self.intake(p)
        with patch.object(pipeline,'execute',side_effect=native_executor):
            for _ in range(4):pipeline.process_one(main)
        attempt=pipeline.claim(main);self.assertEqual(attempt['stage'],'export')
        self.client.post(f"/api/v1/projects/{p['id']}/pipeline/{job['id']}/cancel")
        with self.assertRaisesRegex(RuntimeError,'STALE'):pipeline.export(main,attempt,json.loads(attempt['progress']))
        with main.db() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM artifacts WHERE project_id=?',(p['id'],)).fetchone()[0],0)
        self.assertEqual(list((main.DATA/'exports').glob('*.zip')),[])

    def test_identical_legacy_pdf_can_enter_automatic_revision_processing(self):
        p=self.create();raw=drawing()
        r=self.client.post(f"/api/v1/projects/{p['id']}/sources?version=1",files={'file':('legacy.pdf',raw,'application/pdf')})
        self.assertEqual(r.status_code,200);p=r.json();source=p['sheets'][0]['source_id']
        self.intake(p,raw,replace=source)
        self.assertEqual(self.drain(p)[0]['state'],'DONE')
        current=self.current(p);self.assertEqual(len(current['sheets']),2);self.assertEqual(len(current['materials']),2)

    def test_explicit_reextraction_runs_parser_again_and_keeps_sheet_identities(self):
        p=self.create();self.intake(p);self.drain(p);p=self.current(p)
        ids=[s['id'] for s in p['sheets']]
        response=self.client.post(f"/api/v1/projects/{p['id']}/pipeline/rerun",json={'version':p['version'],'reextract':True})
        self.assertEqual(response.status_code,200,response.text)
        with patch.object(pipeline,'execute',side_effect=native_executor) as execute:
            for _ in range(20):
                if not pipeline.process_one(main):break
        self.assertEqual(sum(c.args[1]=='ocr' for c in execute.call_args_list),2)
        self.assertEqual([s['id'] for s in self.current(p)['sheets']],ids)

    def test_optional_ocr_setup_requires_hosting_operator(self):
        self.assertEqual(self.client.post('/api/v1/system/pipeline/ocr',json={}).json()['state'],'queued')
        with main.db() as conn:conn.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertEqual(self.client.post('/api/v1/system/pipeline/ocr',json={}).status_code,403)
