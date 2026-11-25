"""Unassigned real-source locations never imply a physical route or station.

Generic numbering/support records exercise existing rules, not a 1010 model.
API location checks use the exact reviewed source and actual flange geometry.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

import fitz

from packages.automation.symbols import flange_symbols
from packages.engineering import assigned_nodes, compute_reasons, renumber, topology, topology_assigned, refresh_source_locations, source_location_reviewed
from services.api import main
from tests.integration import test_api as fixtures
from tests.unit.test_engineering import point

SOURCE = Path(__file__).resolve().parents[2] / 'fixtures/1010/1010 Reviewed.pdf'
SHA = '7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59'


class UnassignedEngineeringTests(unittest.TestCase):
    def source_point(self, identifier='source'):
        p = point(0)
        p.update(id=identifier, route=None, order=None, number=None,
                 topology_state='UNASSIGNED', review_label='P-source',
                 origin='automation', verification='proposed')
        return p

    def test_all_point_ids_survive_but_unassigned_locations_never_create_edges_or_numbers(self):
        a = point(1)
        b = point(2)
        source = self.source_point()
        source['number'] = 999  # A stale imported display number is not authority.
        nodes = [a, source, b]
        before = deepcopy(nodes)
        mapping = renumber(nodes)
        graph = topology(nodes)
        self.assertEqual(graph['points'], ['1', 'source', '2'])
        self.assertEqual(graph['unassigned_points'], ['source'])
        self.assertEqual(graph['edges'], [{'from':'1', 'to':'2', 'line_id':'A', 'route':'main'}])
        self.assertEqual([n['number'] for n in nodes], [10, None, 20])
        self.assertEqual(next(m for m in mapping if m['point_id']=='source'), {'point_id':'source','old':999,'new':None})
        for old, new in zip(before, nodes):
            for field in ('id','instances','station_mm','evidence','route','order'):
                self.assertEqual(old[field], new[field])

    def test_all_unassigned_source_points_remain_visible_and_blue_without_a_main_route(self):
        nodes = [self.source_point('a'), self.source_point('b')]
        nodes[0]['source_review_reasons'] = ['SOURCE_INTERFACE_UNCERTAIN']
        compute_reasons(nodes)
        before = deepcopy(nodes)
        renumber(nodes)
        self.assertEqual(assigned_nodes(nodes), [])
        self.assertEqual(topology(nodes)['edges'], [])
        self.assertTrue(all(n['number'] is None for n in nodes))
        for old, new in zip(before, nodes):
            self.assertEqual(old['reasons'], new['reasons'])
            self.assertIn('TOPOLOGY_UNASSIGNED', new['reasons'])
            self.assertIn('SOURCE_PROPOSAL_REVIEW', new['reasons'])
            self.assertIn('UNVERIFIED_DIMENSION', new['reasons'])
        self.assertIn('SOURCE_INTERFACE_UNCERTAIN', nodes[0]['reasons'])

    def test_unassigned_supports_cannot_get_a_six_inch_flag_from_stations_alone(self):
        nodes = [point(0, station='0', kind='support'), point(1, station='25.4', kind='support')]
        for n in nodes:n.update(topology_state='UNASSIGNED', route=None, order=None)
        compute_reasons(nodes)
        self.assertTrue(all(n['support_gap_mm'] is None for n in nodes))
        self.assertTrue(all('SUPPORT_WITHIN_6_IN' not in n['reasons'] for n in nodes))
        self.assertTrue(all(n['station_mm'] is not None for n in nodes))

    def test_branch_cannot_link_to_an_unassigned_takeoff_and_legacy_assignment_stays_compatible(self):
        tee = self.source_point('tee')
        tee['kind'] = 'tee'
        branch = point(2, route='branch-01')
        branch['takeoff_id'] = 'tee'
        self.assertTrue(topology_assigned(branch))
        self.assertFalse(topology_assigned(tee))
        self.assertEqual(topology([tee, branch])['edges'], [])
        legacy = [point(1), point(2)]
        renumber(legacy)
        self.assertEqual([n['number'] for n in legacy], [10,20])
        self.assertEqual(len(topology(legacy)['edges']), 1)

    def test_source_inspection_is_invalidated_by_content_changes_without_losing_its_proof(self):
        source = self.source_point()
        source.update(origin='source-review-profile', source_observation={
            'verification':'reviewed','review_proof':{'sheet_id':'sheet-a','anchor':[10,20],
                'content_hash':['original-stream'],'source_sha256':'original-file',
                'reviewed_by':'rule-test-only','evidence':'Generic source-state contract, not 1010 evidence.'}})
        project = {'nodes':[source],'sheets':[{'id':'sheet-a','content_hash':['original-stream'],'sha256':'original-file'}]}
        self.assertTrue(source_location_reviewed(source, {'sheet-a':project['sheets'][0]}))
        project['sheets'][0]['content_hash'] = ['changed-stream']
        before = deepcopy(source['source_observation']['review_proof'])
        refresh_source_locations(project)
        compute_reasons(project['nodes'])
        self.assertEqual(source['source_observation']['verification'],'proposed')
        self.assertEqual(source['source_observation']['review_history'],[before])
        self.assertIn('SOURCE_LOCATION_REVIEW_REQUIRED',source['reasons'])
        self.assertIn('TOPOLOGY_UNASSIGNED',source['reasons'])


class UnassignedRealSourceApiTests(unittest.TestCase):
    setUp = fixtures.ApiTests.setUp
    tearDown = fixtures.ApiTests.tearDown

    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_bytes()
        assert hashlib.sha256(cls.source).hexdigest() == SHA
        with fitz.open(SOURCE) as source:
            cls.feature = flange_symbols(source[0].get_drawings(), SHA, 0)[0][0]

    def create(self):
        r = self.client.post('/api/v1/projects',json={
            'title':'1010 real-source provisional location contract',
            'line_id':'8-PG-JE3LN2-1010-FUTURE'})
        self.assertEqual(r.status_code,201,r.text)
        p = r.json()
        r = self.client.post(f"/api/v1/projects/{p['id']}/sources?version={p['version']}",
            files={'file':(SOURCE.name,self.source,'application/pdf')})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def body(self, p):
        x,y = self.feature['flange_face']
        return {'version':p['version'],'line_id':p['line_id'],
            'route':None,'order':None,'topology_state':'UNASSIGNED','kind':'flange',
            'dimension':'','evidence':'Real source graphical flange face proposal only. Physical station, material and ordered topology are unproved.',
            'instances':[{'sheet_id':p['sheets'][0]['id'],'anchor':[x,y],'bubble':[x+35,y-35]}]}

    def add(self, p):
        r = self.client.post(f"/api/v1/projects/{p['id']}/nodes",json=self.body(p))
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def source_observation(self, p):
        """Actual recognized source geometry, with neither location nor topology accepted."""
        n = p['nodes'][0]
        sheet = p['sheets'][0]
        n.update(origin='source-review-profile',source_observation={
            'id':'real-source-recognized-flange-face','sheet_id':sheet['id'],
            'anchor':deepcopy(n['instances'][0]['anchor']),'bbox':deepcopy(self.feature['bbox']),
            'source_sha256':SHA,'content_hash':sheet.get('content_hash'),'verification':'proposed'})
        with main.db() as connection:
            connection.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p),p['id']))
        return self.client.get(f"/api/v1/projects/{p['id']}").json()

    def test_actual_source_location_is_saved_with_no_invented_model_order_or_station(self):
        p = self.add(self.create())
        n = p['nodes'][0]
        self.assertEqual(n['instances'][0]['anchor'],self.feature['flange_face'])
        self.assertEqual(n['topology_state'],'UNASSIGNED')
        self.assertEqual(n['verification'],'proposed')
        for field in ('route','order','number','station_mm'):self.assertIsNone(n[field])
        self.assertTrue(n['review_label'].startswith('P-'))
        self.assertIn('TOPOLOGY_UNASSIGNED',n['reasons'])
        self.assertEqual(p['graph']['edges'],[])
        self.assertEqual(p['graph']['points'],[n['id']])
        self.assertTrue(any(i['code']=='NO_REVIEWED_ROUTE' for i in p['issues']))

    def test_presentation_save_without_state_cannot_silently_promote_an_existing_source_point(self):
        p = self.add(self.create())
        before = deepcopy(p['nodes'][0])
        body = self.body(p)
        del body['topology_state']
        body['instances'][0]['bubble'][0] += 10
        r = self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{before['id']}",json=body)
        self.assertEqual(r.status_code,200,r.text)
        p = r.json()
        after = p['nodes'][0]
        for key in ('id','review_label','station_mm','verification','topology_state','route','order','number','reasons'):
            self.assertEqual(after[key],before[key])
        self.assertEqual(after['instances'][0]['anchor'],before['instances'][0]['anchor'])
        self.assertNotEqual(after['instances'][0]['bubble'],before['instances'][0]['bubble'])

    def test_explicit_route_assignment_confirmation_preserves_identity_and_unknown_station(self):
        p = self.add(self.create())
        before = deepcopy(p['nodes'][0])
        body = self.body(p)
        body.update(topology_state='ASSIGNED',route='main',order=1)
        endpoint = f"/api/v1/projects/{p['id']}/nodes/{before['id']}"
        r = self.client.patch(endpoint,json=body)
        self.assertEqual(r.status_code,422,r.text)
        unchanged = self.client.get(f"/api/v1/projects/{p['id']}").json()
        self.assertEqual(unchanged['version'],p['version'])
        self.assertEqual(unchanged['nodes'][0],before)
        body['topology_confirmed'] = True
        r = self.client.patch(endpoint,json=body)
        self.assertEqual(r.status_code,200,r.text)
        after = r.json()['nodes'][0]
        self.assertEqual(after['id'],before['id'])
        self.assertEqual(after['instances'],before['instances'])
        self.assertEqual(after['review_label'],before['review_label'])
        self.assertEqual(after['number'],10)
        self.assertEqual(after['topology_state'],'ASSIGNED')
        self.assertIsNone(after['station_mm'])
        self.assertIn('UNVERIFIED_DIMENSION',after['reasons'])
        self.assertNotIn('TOPOLOGY_UNASSIGNED',after['reasons'])

    def test_unassigned_request_rejects_placeholder_routes_and_new_assigned_points_need_explicit_order(self):
        p = self.create()
        body = self.body(p)
        body.update(route='main',order=1)
        r = self.client.post(f"/api/v1/projects/{p['id']}/nodes",json=body)
        self.assertEqual(r.status_code,422,r.text)
        body.update(topology_state='ASSIGNED',route=None,order=None)
        r = self.client.post(f"/api/v1/projects/{p['id']}/nodes",json=body)
        self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}").json()['nodes'],[])

    def test_route_confirmation_cannot_substitute_for_reviewing_the_actual_source_location(self):
        p = self.source_observation(self.add(self.create()))
        n = deepcopy(p['nodes'][0])
        body = self.body(p)
        body.update(topology_state='ASSIGNED',route='main',order=1,topology_confirmed=True)
        endpoint = f"/api/v1/projects/{p['id']}/nodes/{n['id']}"
        r = self.client.patch(endpoint,json=body)
        self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}").json()['version'],p['version'])
        body['source_location_confirmed'] = True
        r = self.client.patch(endpoint,json=body)
        self.assertEqual(r.status_code,200,r.text)
        after = r.json()['nodes'][0]
        self.assertEqual(after['id'],n['id'])
        self.assertEqual(after['number'],10)
        self.assertEqual(after['source_observation']['verification'],'reviewed')
        proof = after['source_observation']['review_proof']
        self.assertEqual(proof['reviewed_by'],'local-engineer')
        self.assertEqual(proof['source_sha256'],SHA)
        self.assertEqual(proof['anchor'],self.feature['flange_face'])
        self.assertNotIn('SOURCE_LOCATION_REVIEW_REQUIRED',after['reasons'])
        self.assertIsNone(after['station_mm'])
        self.assertIn('UNVERIFIED_DIMENSION',after['reasons'])

    def test_location_only_review_and_bubble_edits_keep_topology_unassigned_then_anchor_changes_invalidate(self):
        p = self.source_observation(self.add(self.create()))
        n = p['nodes'][0]
        endpoint = f"/api/v1/projects/{p['id']}/nodes/{n['id']}"
        body = self.body(p)
        body['source_location_confirmed'] = True
        r = self.client.patch(endpoint,json=body)
        self.assertEqual(r.status_code,200,r.text)
        p = r.json()
        reviewed = deepcopy(p['nodes'][0])
        self.assertNotIn('SOURCE_LOCATION_REVIEW_REQUIRED',reviewed['reasons'])
        self.assertIn('TOPOLOGY_UNASSIGNED',reviewed['reasons'])
        self.assertIsNone(reviewed['number'])
        body = self.body(p)
        body['instances'][0]['bubble'][0] += 12
        r = self.client.patch(endpoint,json=body)
        self.assertEqual(r.status_code,200,r.text)
        p = r.json()
        self.assertEqual(p['nodes'][0]['source_observation'],reviewed['source_observation'])
        body = self.body(p)
        body['instances'][0]['anchor'][0] += 1
        r = self.client.patch(endpoint,json=body)
        self.assertEqual(r.status_code,200,r.text)
        after = r.json()['nodes'][0]
        self.assertEqual(after['source_observation']['verification'],'proposed')
        self.assertEqual(after['source_observation']['review_history'],[reviewed['source_observation']['review_proof']])
        self.assertIn('SOURCE_LOCATION_REVIEW_REQUIRED',after['reasons'])
        self.assertIn('TOPOLOGY_UNASSIGNED',after['reasons'])
        self.assertIsNone(after['station_mm'])


if __name__=='__main__':unittest.main()
