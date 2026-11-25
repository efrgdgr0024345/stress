"""Real-drawing native preview authorization, freshness and graphical-only apply."""
from copy import deepcopy
import json
import unittest
from services.api import main
from tests.integration import test_api as fixtures
from tests.integration import test_1010_source_review as source_fixtures


class NativeLayoutApiTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload
    source=source_fixtures.SourceReviewTests.source
    prepare=source_fixtures.SourceReviewTests.prepare

    def test_real_preview_cache_and_explicit_apply_preserve_every_engineering_fact(self):
        p=self.prepare(self.source());path=f"/api/v1/projects/{p['id']}/pdf-layout"
        self.assertIsNone(self.client.get(path).json()['accepted'])
        self.assertEqual(self.client.post(path+'/preview',json={'version':1,'confirmed':True}).status_code,409)
        response=self.client.post(path+'/preview',json={'version':p['version'],'confirmed':True})
        self.assertEqual(response.status_code,200,response.text);plan=response.json()
        self.assertTrue(plan['can_export'],plan['issues'])
        token=plan['proposal_sha256'];query=f"?version={p['version']}&proposal_sha256={token}"
        pdf=self.client.get(path+'/native.pdf'+query);self.assertEqual(pdf.status_code,200,pdf.text[:200] if pdf.status_code!=200 else '')
        self.assertTrue(pdf.content.startswith(b'%PDF-'))
        manifest=self.client.get(path+'/manifest'+query).json()
        self.assertEqual(len(manifest['annotations']),plan['summary']['generated_objects'])
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}").json()['version'],p['version'])
        bad={'version':p['version'],'proposal_sha256':'a'*64,'reason':'SOFTWARE VALIDATION of graphical placement only.','confirmed':True}
        self.assertEqual(self.client.post(path+'/accept',json=bad).status_code,422)
        before=deepcopy(p)
        response=self.client.post(path+'/accept',json={**bad,'proposal_sha256':token})
        self.assertEqual(response.status_code,200,response.text);p=response.json()
        for prior,current in zip(before['nodes'],p['nodes']):
            for key in ('id','number','line_id','kind','route','order','station_mm','coordinates_mm','evidence','source_observation'):
                self.assertEqual(prior.get(key),current.get(key),key)
            self.assertEqual([(i['sheet_id'],i['anchor']) for i in prior['instances']],[(i['sheet_id'],i['anchor']) for i in current['instances']])
        self.assertTrue(self.client.get(path).json()['accepted']['current'])
        self.assertFalse(p.get('review_approval'))
        self.assertEqual(self.client.get(path+'/native.pdf'+query).status_code,409)
        response=self.client.post(path+'/preview',json={'version':p['version'],'confirmed':True})
        self.assertEqual(response.status_code,200,response.text);current=response.json()
        cache=main.DATA/'pdf-layout-previews'/p['id']/f"r{p['version']}-{current['proposal_sha256']}"/'metadata.json'
        metadata=json.loads(cache.read_text());metadata['annotations'][0]['role']='tampered';cache.write_text(json.dumps(metadata))
        query=f"?version={p['version']}&proposal_sha256={current['proposal_sha256']}"
        self.assertEqual(self.client.get(path+'/manifest'+query).status_code,409)

    def test_viewers_cannot_generate_or_accept_and_other_tenants_cannot_read(self):
        p=self.prepare(self.source());path=f"/api/v1/projects/{p['id']}/pdf-layout"
        with main.db() as conn:conn.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.client.post(path+'/preview',json={'version':p['version'],'confirmed':True}).status_code,403)
        with main.db() as conn:conn.execute("UPDATE projects SET tenant='another-tenant' WHERE id=?",(p['id'],))
        self.assertEqual(self.client.get(path).status_code,404)
