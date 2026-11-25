"""Actual printed 1010 XYZ is accepted only after explicit source inspection."""
from copy import deepcopy
from decimal import Decimal
import io
import unittest
from openpyxl import load_workbook
from tests.integration import test_api as fixtures
from tests.integration import test_1010_source_review as source_fixtures
from packages.physical.constraints import solve


class PrintedCoordinateTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload
    source=source_fixtures.SourceReviewTests.source
    prepare=source_fixtures.SourceReviewTests.prepare

    def model(self):
        p=self.prepare(self.source())
        candidate=next(c for c in p['automation']['continuation_candidates'] if c['source_label']=='S1-CONT-SHEET2')
        return p,candidate

    def inspect(self,p,c):
        n=next(n for n in p['nodes'] if n['id']==c['point_id'])
        body={'version':p['version'],'topology_state':'UNASSIGNED','line_id':n['line_id'],'route':None,'order':None,
            'kind':n['kind'],'dimension':'','instances':n['instances'],'source_location_confirmed':True,'source_location_sheet_id':c['sheet_id'],
            'evidence':'SOFTWARE VALIDATION of the actual source coordinate leader and anchor. No station, topology or lead-engineer approval is accepted.'}
        r=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{n['id']}",json=body)
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def accept(self,p,c):
        return self.client.post(f"/api/v1/projects/{p['id']}/physical-model/source-coordinates/{c['id']}/accept",json={
            'version':p['version'],'tolerance_text':'0 mm','confirmed':True,
            'evidence':'SOFTWARE VALIDATION: explicit printed E135 ft 4-1/4in, S312 ft 10-3/8in and EL37 ft 10-3/4in; source only, no engineering approval.'})

    def test_source_inspection_precedes_acceptance_and_all_unknowns_stay_blank(self):
        p,c=self.model();before=deepcopy(p['nodes'])
        self.assertEqual(self.accept(p,c).status_code,409)
        p=self.inspect(p,c);r=self.accept(p,c);self.assertEqual(r.status_code,200,r.text);p=r.json()
        coordinate=next(v for v in solve(p)['coordinates'] if v['point_id']==c['point_id'])
        self.assertEqual({a:Decimal(v['value_mm']) for a,v in coordinate['axes'].items()},
            {'X':Decimal('41255.95'),'Y':Decimal('-95361.125'),'Z':Decimal('11550.65')})
        self.assertEqual(len(p['physical_model']['constraints']),3)
        self.assertEqual([n['instances'] for n in p['nodes']],[n['instances'] for n in before])
        self.assertTrue(all(n['station_mm'] is None and n['number'] is None and n['route'] is None for n in p['nodes']))
        self.assertEqual(p['graph']['edges'],[])
        report=self.client.get(f"/api/v1/projects/{p['id']}/physical-model/source-coordinates").json()
        self.assertEqual(len(report['proposals']),12)
        self.assertEqual(sum(v['status']=='ACCEPTED' for v in report['proposals']),3)
        r=self.accept(p,c);self.assertEqual(r.status_code,200,r.text);self.assertEqual(len(r.json()['physical_model']['constraints']),3)
        r=self.client.get(f"/api/v1/projects/{p['id']}/results/workbook");self.assertEqual(r.status_code,200)
        book=load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
        rows=list(book['Nodes'].iter_rows(min_row=6,values_only=True));row=next(row for row in rows if row[13]==c['point_id'])
        self.assertAlmostEqual(row[5],41255.95);self.assertAlmostEqual(row[6],-95361.125);self.assertAlmostEqual(row[7],11550.65)
        self.assertIsNone(row[4]);self.assertIsNone(row[0]);book.close()

    def test_changed_anchor_invalidates_coordinate_use_until_source_is_reinspected_and_reaccepted(self):
        p,c=self.model();p=self.inspect(p,c);p=self.accept(p,c).json()
        n=next(n for n in p['nodes'] if n['id']==c['point_id']);instances=deepcopy(n['instances']);instances[0]['anchor'][0]+=1
        body={'version':p['version'],'topology_state':'UNASSIGNED','line_id':n['line_id'],'route':None,'order':None,'kind':n['kind'],
            'dimension':'','instances':instances,'evidence':'SOFTWARE VALIDATION corrected source visual anchor; previous printed coordinate acceptance must become stale.'}
        r=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{n['id']}",json=body);self.assertEqual(r.status_code,200,r.text);p=r.json()
        self.assertTrue(any(i['code']=='SOURCE_COORDINATE_REVIEW_STALE' for i in solve(p)['issues']))
        coordinate=next(v for v in solve(p)['coordinates'] if v['point_id']==c['point_id'])
        self.assertTrue(all(v['value_mm'] is None for v in coordinate['axes'].values()))
        self.assertEqual(self.accept(p,c).status_code,409)
        p=self.inspect(p,c);r=self.accept(p,c);self.assertEqual(r.status_code,200,r.text)
        self.assertFalse(any(i['code']=='SOURCE_COORDINATE_REVIEW_STALE' for i in solve(r.json())['issues']))
