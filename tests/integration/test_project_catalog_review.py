"""Actual PDF/catalog source review in disposable projects; no real engineering signoff."""
from copy import deepcopy
import hashlib
import unittest

from tests.integration import test_api as fixture
from tests.unit.test_project_catalog_review import CATALOG,PRIVATE_CATALOG,SOURCE_SHA256,EVIDENCE
from tests.integration.test_1010_source_review import SOURCE
from tests.integration import test_workflows as workflow_fixture


class ProjectCatalogReviewApiTests(unittest.TestCase):
    setUp=fixture.ApiTests.setUp
    tearDown=fixture.ApiTests.tearDown
    upload=fixture.ApiTests.upload

    def source(self):
        catalog_path=CATALOG if CATALOG.is_file() else PRIVATE_CATALOG
        raw=catalog_path.read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),SOURCE_SHA256)
        r=self.client.post('/api/v1/catalogs/import',files={'file':(catalog_path.name,raw,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
        self.assertEqual(r.status_code,200,r.text);catalog=r.json()
        r=self.client.post('/api/v1/projects',json={'title':'SOFTWARE ONLY real1010 source/catalog review',
            'line_id':'8-PG-JE3LN2-1010-FUTURE'})
        self.assertEqual(r.status_code,201,r.text);p=self.upload(r.json(),SOURCE.read_bytes())
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/source-points",json={'version':p['version'],'confirmed':True})
        self.assertEqual(r.status_code,200,r.text)
        return r.json(),catalog

    def path(self,p):return f"/api/v1/projects/{p['id']}/catalog-review"
    def report(self,p):
        r=self.client.get(self.path(p));self.assertEqual(r.status_code,200,r.text);return r.json()

    def prepare(self,p):
        r=self.client.post(self.path(p)+'/prepare',json={'version':p['version'],'confirmed':True})
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def decision(self,p,row,decision='DECLARE_NA',**changes):
        body={'version':p['version'],'material_id':row['material_id'],'decision':decision,
            'reason_code':'CATALOG_FACING_UNSPECIFIED' if row['family']=='flange' else 'VALVE_MANUFACTURER_DATA_UNAVAILABLE',
            'evidence':EVIDENCE,'confirmed':True,'source_context_sha256':row['source_context_sha256']}
        if decision=='REOPEN':body['reason_code']='REVIEW_REOPENED'
        body.update(changes);return self.client.post(self.path(p)+'/decision',json=body)

    def test_actual627_source_preparation_and_all18_na_occurrences_keep_unknown_geometry_and_no_approvals(self):
        p,catalog=self.source();original_nodes=deepcopy(p['nodes']);original_graph=deepcopy(p['graph'])
        report=self.report(p)
        self.assertEqual(sum(v['record_count'] for v in report['catalog_manifest']),627)
        self.assertEqual(len(report['rows']),6);self.assertEqual(len(report['occurrences']),18)
        self.assertEqual([len(s['rows']) for s in report['sheets']],[2,4])
        self.assertEqual(len(report['classification_rows']),1)
        self.assertTrue(all(not r['exact_candidates'] for r in report['rows']))
        self.assertEqual(self.decision(p,report['rows'][0]).status_code,422)
        p=self.prepare(p)
        for row in self.report(p)['rows']:
            response=self.decision(p,row);self.assertEqual(response.status_code,200,response.text);p=response.json()
        report=self.report(p);self.assertEqual(len(report['reviews']),6)
        self.assertTrue(report['summary']['review_complete']);self.assertFalse(report['summary']['numeric_complete'])
        self.assertTrue(all(r['status']=='DECLARED_NA' and r['latest_review']['current'] for r in report['rows']))
        self.assertTrue(all(not any(r['values'].values()) and not r['engineering_approved'] for r in report['occurrences']))
        self.assertTrue(all(r['project_manufacturer']['status']=='UNCONFIRMED' for r in report['rows']))
        self.assertEqual(p['nodes'],original_nodes);self.assertEqual(p['graph'],original_graph)
        self.assertTrue(all(not m.get('catalog_match') for m in p['materials']))
        versions=self.client.get(f"/api/v1/catalogs/{catalog['id']}/versions").json()
        self.assertTrue(all(v['data']['approval'] is None and v['data']['status']=='PENDING_APPROVAL' for v in versions))
        self.assertEqual(hashlib.sha256((fixture.main.DATA/'catalogs'/f"{catalog['id']}.xlsx").read_bytes()).hexdigest(),SOURCE_SHA256)

    def test_partial_candidates_and_catalog_quality_cannot_be_accepted_as_exact_or_as_project_maker(self):
        p,_=self.source();p=self.prepare(p);row=next(r for r in self.report(p)['rows'] if r['family']=='flange')
        candidate=row['partial_candidates'][0]
        r=self.decision(p,row,'ACCEPT_EXACT_MATCH',reason_code='SOURCE_SPECIFICATION_AND_DATASET_REVIEWED',
            catalog_version_id=candidate['catalog_version_id'],record_id=candidate['record_id'])
        self.assertEqual(r.status_code,422,r.text)
        maker={'version':p['version'],'material_id':row['material_id'],'decision':'CONFIRM',
            'evidence':EVIDENCE,'confirmed':True,'source_context_sha256':row['source_context_sha256']}
        self.assertEqual(self.client.post(self.path(p)+'/manufacturer',json=maker).status_code,422)
        maker['decision']='REOPEN';r=self.client.post(self.path(p)+'/manufacturer',json=maker)
        self.assertEqual(r.status_code,200,r.text);p=r.json();report=self.report(p)
        self.assertEqual(len(report['manufacturer_reviews']),1)
        self.assertTrue(all(row['project_manufacturer']['status']=='UNCONFIRMED' for row in report['rows']))
        self.assertFalse(p.get('review_approval'))

    def test_source_context_versions_permissions_and_tenant_isolation_guard_reviews(self):
        p,_=self.source();p=self.prepare(p);row=self.report(p)['rows'][0]
        r=self.decision(p,row);self.assertEqual(r.status_code,200,r.text);updated=r.json()
        self.assertEqual(self.decision(p,row).status_code,409)
        material=next(m for m in updated['materials'] if m['id']==row['material_id'])
        body={k:deepcopy(material.get(k)) for k in ('sheet_id','item_no','family','description','size','quantity','observed','evidence',
            'quantity_value','quantity_unit','observed_quantity_value')}
        body.update(version=updated['version'],size='10')
        r=self.client.patch(f"/api/v1/projects/{p['id']}/materials/{material['id']}",json=body)
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        report=self.report(p);self.assertEqual(next(r for r in report['rows'] if r['material_id']==row['material_id'])['status'],'REVIEW_STALE')
        self.assertEqual(self.decision(p,row).status_code,422)
        with fixture.main.db() as conn:conn.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertFalse(self.report(p)['can_edit']);self.assertEqual(self.decision(p,row).status_code,403)
        self.assertEqual(self.client.post(self.path(p)+'/prepare',json={'version':p['version'],'confirmed':True}).status_code,403)
        with fixture.main.db() as conn:conn.execute('UPDATE projects SET tenant=? WHERE id=?',('foreign-tenant',p['id']))
        self.assertEqual(self.client.get(self.path(p)).status_code,404)

    def test_changed_registered_workbook_stales_na_receipt_without_replacing_source_or_approval(self):
        p,catalog=self.source();p=self.prepare(p);row=self.report(p)['rows'][0]
        r=self.decision(p,row);self.assertEqual(r.status_code,200,r.text);p=r.json()
        (fixture.main.DATA/'catalogs'/f"{catalog['id']}.xlsx").write_bytes(b'SOFTWARE TEST ONLY: altered private catalog bytes')
        report=self.report(p)
        self.assertTrue(all(not v['integrity_current'] for v in report['catalog_manifest']))
        self.assertEqual(next(v for v in report['rows'] if v['material_id']==row['material_id'])['status'],'REVIEW_STALE')
        self.assertTrue(all(not any(v['values'].values()) for v in report['rows']))
        self.assertTrue(all(v['project_manufacturer']['status']=='UNCONFIRMED' for v in report['rows']))

    def test_explicit_exact_match_uses_the_reviewed_dataset_but_maker_confirmation_stays_separate(self):
        # Existing generic software workbook/PDF inputs, not a real 1010
        # manufacturer, station, or component record.
        _,dataset,_=workflow_fixture.Workflows.dataset(self,confirmed=True)
        response=self.client.post(f"/api/v1/catalog-versions/{dataset['id']}/approve",json={'reason':EVIDENCE})
        self.assertEqual(response.status_code,200,response.text)
        response=self.client.post('/api/v1/projects',json={'title':'SOFTWARE ONLY generic exact catalog API vector','line_id':'SOFTWARE-ONLY-LINE'})
        self.assertEqual(response.status_code,201,response.text)
        p=self.upload(response.json(),fixture.ApiTests.pdf(self))
        response=self.client.post(f"/api/v1/projects/{p['id']}/materials",json={'version':p['version'],
            'sheet_id':p['sheets'][0]['id'],'item_no':'SOFTWARE-ONLY-ITEM','family':'flange',
            'description':'SOFTWARE ONLY FLANGE WN RF CLASS150 ASME B16.5','size':'8','quantity':1,
            'observed':0,'evidence':EVIDENCE})
        self.assertEqual(response.status_code,200,response.text);p=self.prepare(response.json())
        row=self.report(p)['rows'][0];candidate=row['exact_candidates'][0]
        response=self.decision(p,row,'ACCEPT_EXACT_MATCH',reason_code='SOURCE_SPECIFICATION_AND_DATASET_REVIEWED',
            catalog_version_id=candidate['catalog_version_id'],record_id=candidate['record_id'])
        self.assertEqual(response.status_code,200,response.text);p=response.json()
        row=self.report(p)['rows'][0];self.assertEqual(row['status'],'MATCHED_REFERENCE')
        self.assertEqual(row['values']['weight_n'],'100');self.assertEqual(row['values']['half_weight_n'],'140')
        self.assertEqual(row['catalog_source_quality'],'MANUFACTURER_CONFIRMED')
        self.assertEqual(row['project_manufacturer']['status'],'UNCONFIRMED')
        match=next(m for m in p['materials'] if m['id']==row['material_id'])['catalog_match']
        self.assertEqual(match['status'],'REFERENCE_ONLY')
        body={'version':p['version'],'material_id':row['material_id'],'decision':'CONFIRM',
            'vendor':'Synthetic manufacturer','model':'SYN-001','evidence':EVIDENCE,
            'confirmed':True,'source_context_sha256':row['source_context_sha256']}
        response=self.client.post(self.path(p)+'/manufacturer',json=body)
        self.assertEqual(response.status_code,200,response.text);p=response.json()
        self.assertEqual(self.report(p)['rows'][0]['project_manufacturer']['status'],'CONFIRMED')
        self.assertEqual(next(m for m in p['materials'] if m['id']==row['material_id'])['catalog_match']['status'],'REFERENCE_ONLY')
