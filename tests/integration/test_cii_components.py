"""Native input workflow on actual source drafts and labelled software-only vectors."""
from copy import deepcopy
import json
import unittest

from packages.automation.recognize import identity
from tests.integration import test_api as fixture
from tests.integration import test_1010_source_review as source_fixture
from tests.unit.test_cii_components import software_model,record_inputs,EVIDENCE


class CiiComponentApiTests(unittest.TestCase):
    setUp=fixture.ApiTests.setUp
    tearDown=fixture.ApiTests.tearDown
    create=fixture.ApiTests.create
    upload=fixture.ApiTests.upload
    source=source_fixture.SourceReviewTests.source
    prepare=source_fixture.SourceReviewTests.prepare

    def path(self,p):return f"/api/v1/projects/{p['id']}/cii-components"
    def report(self,p):
        response=self.client.get(self.path(p));self.assertEqual(response.status_code,200,response.text);return response.json()

    def draft(self,p):
        req=next(r for r in self.report(p)['requirements'] if r['kind']=='BEND')
        return {'version':p['version'],'kind':'BEND','component_id':req['component_id'],
            'point_id':None,'element_id':None,'source_sheet_id':req['sheet_id'],'review_state':'DRAFT',
            'values':{'radius_mm':None},'evidence':'SOFTWARE VALIDATION ONLY: actual source COD, radius and native bend geometry/field contracts remain unknown; no engineering acceptance.',
            'confirmed':True}

    def test_actual_source_can_persist_a_null_bend_draft_but_never_invent_a_native_far_end(self):
        p=self.prepare(self.source());before=deepcopy(p['nodes']);body=self.draft(p)
        response=self.client.post(self.path(p)+'/records',json=body)
        self.assertEqual(response.status_code,200,response.text);p=response.json();report=self.report(p)
        self.assertEqual(len(report['records']),1);record=report['records'][0]
        self.assertEqual(record['review_state'],'DRAFT');self.assertIsNone(record['values']['radius_mm'])
        self.assertFalse(record['ready']);self.assertTrue(record['current'])
        self.assertTrue({'NATIVE_COMPONENT_DRAFT','BEND_NATIVE_GEOMETRY_CONTRACT_UNVERIFIED','BEND_NEUTRAL_FIELD_LAYOUT_AMBIGUOUS'}<=
            {i['code'] for i in record['issues']})
        self.assertEqual(p['nodes'],before);self.assertFalse(p.get('review_approval'))
        response=self.client.get(f"/api/v1/projects/{p['id']}/results/caesar-neutral")
        self.assertEqual(response.status_code,422,response.text);self.assertIn('BEND',response.text)
        body.update(version=p['version'],review_state='REVIEWED',values={'radius_mm':'100','representation_note':'A checkbox cannot resolve the missing official native bend contract.'})
        response=self.client.patch(self.path(p)+'/records/'+record['id'],json=body)
        self.assertEqual(response.status_code,200,response.text);p=response.json()
        self.assertFalse(self.report(p)['records'][0]['ready'])
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}/results/caesar-neutral").status_code,422)
        self.assertEqual(p['nodes'],before)

    def test_record_versions_source_context_and_withdrawal_history_are_explicit(self):
        p=self.prepare(self.source());body=self.draft(p)
        response=self.client.post(self.path(p)+'/records',json=body);self.assertEqual(response.status_code,200,response.text);p=response.json()
        self.assertEqual(self.client.post(self.path(p)+'/records',json=body).status_code,409)
        record=self.report(p)['records'][0];sheet=p['sheets'][0]
        response=self.client.patch(f"/api/v1/projects/{p['id']}/sheets/{sheet['id']}",json={
            'version':p['version'],'printed_id':sheet['printed_id']+' SOFTWARE REVIEW','line_id':sheet['line_id'],
            'axis':sheet.get('axis'),'table':sheet.get('table')})
        self.assertEqual(response.status_code,200,response.text);p=response.json()
        self.assertTrue(self.report(p)['records'][0]['stale'])
        response=self.client.request('DELETE',self.path(p)+'/records/'+record['id'],json={
            'version':p['version'],'confirmed':True,'reason':'SOFTWARE VALIDATION ONLY: withdraw the unproved native draft and preserve its source evidence.'})
        self.assertEqual(response.status_code,200,response.text);p=response.json()
        self.assertEqual(self.report(p)['records'],[])
        self.assertEqual(p['analysis_model']['native_component_history'][-1]['record']['id'],record['id'])

    def test_explicit_software_only_rigid_tee_restraint_candidate_requires_every_reviewed_record(self):
        p=self.create();model=software_model(with_records=False)
        # Import the existing labelled pure-rule vector into this disposable
        # project; it never becomes a real1010 fixture or engineering result.
        model['id']=p['id']
        for element in model['analysis_model']['elements']:
            element['id']=identity(model['id'],element['from_point_id'],element['to_point_id'])
        for key in ('line_id','nodes','sheets','materials','analysis_model'):p[key]=deepcopy(model[key])
        p['title']='SOFTWARE ONLY native-component API vector'
        with fixture.main.db() as conn:
            conn.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p),p['id']))
            conn.execute('UPDATE revisions SET data=? WHERE id=? AND version=?',(json.dumps(p),p['id'],p['version']))
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}/results/caesar-neutral").status_code,422)
        for data in record_inputs(p):
            body={**data,'version':p['version'],'component_id':None,'source_sheet_id':'SOFTWARE-ONLY-SHEET',
                'review_state':'REVIEWED','evidence':EVIDENCE,'confirmed':True}
            response=self.client.post(self.path(p)+'/records',json=body)
            self.assertEqual(response.status_code,200,response.text);p=response.json()
        report=self.report(p);self.assertTrue(all(r['ready'] for r in report['records']),report['issues'])
        response=self.client.get(f"/api/v1/projects/{p['id']}/results/caesar-neutral")
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn(b'#$ RIGID',response.content);self.assertIn(b'#$ RESTRANT',response.content)
        self.assertFalse(report['native_generation_is_application_qualified'])
        self.assertFalse(p.get('review_approval'))

    def test_unknown_fields_foreign_ids_viewer_and_tenant_access_are_rejected(self):
        p=self.prepare(self.source());body=self.draft(p)
        self.assertEqual(self.client.post(self.path(p)+'/records',json={**body,'values':{'invented_radius':'100'}}).status_code,422)
        self.assertEqual(self.client.post(self.path(p)+'/records',json={**body,'point_id':'foreign-or-deleted-point'}).status_code,422)
        with fixture.main.db() as conn:conn.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertFalse(self.report(p)['can_edit'])
        self.assertEqual(self.client.post(self.path(p)+'/records',json=body).status_code,403)
        with fixture.main.db() as conn:conn.execute('UPDATE projects SET tenant=? WHERE id=?',('foreign-tenant',p['id']))
        self.assertEqual(self.client.get(self.path(p)).status_code,404)
