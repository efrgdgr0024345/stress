"""Per-sheet review mechanics on real source anchors, not an accepted 1010 identity."""
from copy import deepcopy
import json
import unittest
from tests.integration import test_api as fixtures
from tests.integration import test_1010_source_review as source_fixtures
from packages.engineering import source_location_reviewed,source_observations
from services.api import main


class MultipleSourceInspectionTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload
    source=source_fixtures.SourceReviewTests.source
    prepare=source_fixtures.SourceReviewTests.prepare

    def body(self,p,n,sheet):
        return {'version':p['version'],'line_id':n['line_id'],'topology_state':'UNASSIGNED',
            'route':None,'order':None,'kind':n['kind'],'dimension':'','instances':n['instances'],
            'evidence':'SOFTWARE ONLY per-sheet source-inspection contract. No engineering identity, coordinate, station or topology is accepted.',
            'source_location_confirmed':True,'source_location_sheet_id':sheet}

    def test_primary_and_secondary_source_inspections_are_independent_and_editable(self):
        p=self.prepare(self.source())
        candidates={c['source_label']:c for c in p['automation']['continuation_candidates']}
        a=next(n for n in p['nodes'] if n['id']==candidates['S1-CONT-SHEET2']['point_id'])
        b=next(n for n in p['nodes'] if n['id']==candidates['S2-CONT-SHEET1']['point_id'])
        # Construct an UNACCEPTED shared-source software state solely to exercise
        # separate review records. It never becomes an engineering identity link.
        a['source_observations']=[deepcopy(a['source_observation']),deepcopy(b['source_observation'])]
        a['instances']+=deepcopy(b['instances']);p['nodes'].remove(b);p.setdefault('point_aliases',{})[b['id']]=a['id']
        with main.db() as c:c.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p),p['id']))
        first,second=[i['sheet_id'] for i in a['instances']]
        for sheet in (first,second):
            r=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{a['id']}",json=self.body(p,a,sheet))
            self.assertEqual(r.status_code,200,r.text);p=r.json();a=next(n for n in p['nodes'] if n['id']==a['id'])
            observations={o['sheet_id']:o for o in source_observations(a)}
            self.assertEqual(observations[sheet]['verification'],'reviewed')
            self.assertEqual(source_location_reviewed(a),sheet==second)
        original_primary=deepcopy(a['source_observation']['review_proof'])
        a['instances'][1]['anchor'][0]+=1
        r=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{a['id']}",json=self.body(p,a,second))
        self.assertEqual(r.status_code,200,r.text);p=r.json();a=next(n for n in p['nodes'] if n['id']==a['id'])
        self.assertEqual(a['source_observation']['review_proof'],original_primary)
        self.assertTrue(source_location_reviewed(a))
        self.assertEqual(a['topology_state'],'UNASSIGNED');self.assertIsNone(a['number']);self.assertIsNone(a['station_mm'])
        self.assertEqual(p['graph']['edges'],[]);self.assertFalse(p.get('continuations'))

    def test_legacy_link_tool_cannot_bypass_a_source_point_continuation_review(self):
        p=self.prepare(self.source());n=p['nodes'][0];body=self.body(p,n,p['sheets'][0]['id'])
        body['instances']=deepcopy(n['instances'])+[{'sheet_id':p['sheets'][1]['id'],'anchor':[100,100],'bubble':[140,140]}]
        r=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{n['id']}",json=body)
        self.assertEqual(r.status_code,422,r.text)
        after=self.client.get(f"/api/v1/projects/{p['id']}").json()
        self.assertEqual(after['version'],p['version']);self.assertEqual(after['nodes'],p['nodes'])
