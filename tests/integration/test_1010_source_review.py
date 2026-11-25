"""The actual reviewed source has source proposals, never a fabricated golden model."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import unittest
import zipfile
from openpyxl import load_workbook
from tests.integration import test_api as fixtures
from packages.physical import audit
from packages.physical.source_review import source_profile,incoming_materials
from packages.engineering import topology

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'


class SourceReviewTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload
    pdf=fixtures.ApiTests.pdf

    def source(self):
        p=self.upload(self.create(),SOURCE.read_bytes())
        return p

    def prepare(self,p):
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/source-points",json={'version':p['version'],'confirmed':True})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def test_all_real_required_ports_are_proposed_or_have_typed_source_exceptions(self):
        p=self.prepare(self.source());model=audit(p)
        self.assertEqual(len(model['components']),40)
        self.assertEqual(sum(len(c['ports']) for c in model['components']),60)
        self.assertEqual(sum(bool(port) for c in model['components'] for port in c['ports'].values()),55)
        unlocated=[(c,key) for c in model['components'] for key,value in c['ports'].items() if value is None]
        self.assertEqual(len(unlocated),5)
        self.assertTrue(all(c['kind']=='elbow' and key=='theoretical_cod' for c,key in unlocated))
        for c,key in unlocated:
            issues=[i for i in model['issues'] if i.get('component_id')==c['id'] and i.get('port')==key]
            self.assertTrue(issues)
            self.assertTrue(all(i['color']=='blue' and i['source_sha256']==source_profile()['source_sha256'] for i in issues))
        self.assertEqual(len(p['nodes']),47)
        self.assertTrue(all(n['station_mm'] is None and n['route'] is None and n['order'] is None and n['number'] is None for n in p['nodes']))
        self.assertTrue(all(n['reasons'] and n['source_observation']['verification']=='proposed' for n in p['nodes']))
        self.assertEqual(topology(p['nodes'])['edges'],[])
        self.assertEqual(len(topology(p['nodes'])['points']),47)
        self.assertFalse(p['source_review']['engineering_approved'])
        pv=next(c for c in model['components'] if c['kind']=='inline_component_unclassified')
        self.assertEqual(set(pv['ports']),{'process_in','process_out'})
        self.assertTrue(any(i['code']=='COMPONENT_CLASSIFICATION_REQUIRED' and i.get('material_id')==pv['material_id'] for i in model['issues']))
        # Three DBB ends and PIT stay distinct even where graphic positions are close.
        pit=next(c for c in model['components'] if c['kind']=='single_instrument')
        pit_id=pit['ports']['process_connection']['point_id']
        dbb=[c for c in model['components'] if c['kind']=='valve' and c['item_no']=='9']
        self.assertTrue(all(pit_id not in {v['point_id'] for v in c['ports'].values() if v} for c in dbb))
        r=self.client.get(f"/api/v1/projects/{p['id']}/results/workbook")
        self.assertEqual(r.status_code,200,r.text[:200] if r.status_code!=200 else '')
        book=load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
        self.assertEqual(book['Nodes'].max_row,52);self.assertEqual(book['Component ports'].max_row,65)
        self.assertTrue(all(row[0] is None and row[4] is None for row in book['Nodes'].iter_rows(min_row=6,values_only=True)))
        self.assertEqual(book['CAESAR input'].max_row,6);book.close()
        self.assertEqual(hashlib.sha256(self.client.get(f"/api/v1/projects/{p['id']}/sources/{p['sheets'][0]['source_id']}").content).hexdigest(),source_profile()['source_sha256'])

    def test_prepare_is_idempotent_preserves_engineer_changes_and_respects_deletion(self):
        p=self.prepare(self.source());before=deepcopy(p['nodes'])
        p=self.prepare(p);self.assertEqual(p['nodes'],before)
        point=p['nodes'][0];r=self.client.delete(f"/api/v1/projects/{p['id']}/nodes/{point['id']}?version={p['version']}")
        self.assertEqual(r.status_code,200,r.text);p=self.prepare(r.json())
        self.assertEqual(len(p['nodes']),46)
        self.assertNotIn(point['id'],{n['id'] for n in p['nodes']})
        self.assertTrue(any(i['check']=='UNLOCATED_INTERFACE' for i in audit(p)['issues']))

    def test_wrong_source_never_receives_the_real_source_profile_and_viewer_cannot_prepare(self):
        p=self.upload(self.create())
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/source-points",json={'version':p['version'],'confirmed':True})
        self.assertEqual(r.status_code,409,r.text)
        p=self.source()
        with fixtures.main.db() as c:c.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/source-points",json={'version':p['version'],'confirmed':True})
        self.assertEqual(r.status_code,403)

    def test_fresh_ocr_cannot_duplicate_source_inventory_or_overwrite_reviewed_materials(self):
        p=self.prepare(self.source())
        incoming=deepcopy(p['materials'])
        for m in incoming:m['id']='fresh-ocr-'+m['id']
        self.assertEqual(incoming_materials(p,incoming),[])
        changed=deepcopy(p)
        for s in changed['sheets']:s['sha256']='a'*64
        self.assertEqual(incoming_materials(changed,incoming),incoming)
