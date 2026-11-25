"""The exact 1010 source is reviewed in disposable software projects, never approved."""
from copy import deepcopy
from pathlib import Path
import unittest

from tests.integration import test_api as fixture

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'
REASON='SOFTWARE VALIDATION ONLY: explicit disposable source pair order, not a real 1010 route or engineering approval.'


class TopologyReviewApiTests(unittest.TestCase):
    setUp=fixture.ApiTests.setUp
    tearDown=fixture.ApiTests.tearDown
    upload=fixture.ApiTests.upload

    def source(self):
        r=self.client.post('/api/v1/projects',json={'title':'SOFTWARE ONLY actual 1010 topology review contract',
            'line_id':'8-PG-JE3LN2-1010-FUTURE'})
        self.assertEqual(r.status_code,201,r.text)
        p=self.upload(r.json(),SOURCE.read_bytes())
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/source-points",
            json={'version':p['version'],'confirmed':True})
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        proposals=self.client.get(f"/api/v1/projects/{p['id']}/physical-model/stations").json()['proposals']
        proposal=next((v for v in proposals if v['source_text']=='2"'),proposals[0])
        return p,[proposal['from_point_id'],proposal['to_point_id']]

    def path(self,p):return f"/api/v1/projects/{p['id']}/topology-review"

    def inspect(self,p,ids):
        for uid in ids:
            node=next(n for n in p['nodes'] if n['id']==uid)
            body={k:deepcopy(node.get(k)) for k in ('line_id','kind','instances')}
            body.update(version=p['version'],topology_state='UNASSIGNED',route=None,order=None,takeoff_id=None,
                dimension='',evidence=REASON,source_location_confirmed=True,
                source_location_sheet_id=node['instances'][0]['sheet_id'])
            r=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{uid}",json=body)
            self.assertEqual(r.status_code,200,r.text);p=r.json()
        return p

    def body(self,p,ids):
        nodes={n['id']:n for n in p['nodes']}
        return {'version':p['version'],'reason':REASON,'confirmed':True,
            'assignments':[{'point_id':uid,'line_id':nodes[uid]['line_id'],'topology_state':'ASSIGNED',
                'route':'main','order':index,'takeoff_id':None,'topology_confirmed':True}
                for index,uid in enumerate(ids)]}

    def test_real_source_is_visible_but_preview_cannot_bulk_approve_source_inspection(self):
        p,ids=self.source();r=self.client.get(self.path(p));self.assertEqual(r.status_code,200,r.text)
        report=r.json();self.assertEqual(len(report['points']),47)
        self.assertTrue(all(not n['source_location_reviewed'] for n in report['points']))
        self.assertEqual(report['graph']['edges'],[])
        self.assertEqual(report['summary']['unassigned'],47)
        r=self.client.post(self.path(p)+'/preview',json=self.body(p,ids))
        self.assertEqual(r.status_code,422,r.text)
        current=self.client.get(f"/api/v1/projects/{p['id']}").json()
        self.assertEqual(current['version'],p['version']);self.assertEqual(current['nodes'],p['nodes'])

    def test_source_inspection_preview_apply_and_repeat_numbering_preserve_physical_facts(self):
        p,ids=self.source();p=self.inspect(p,ids);before=deepcopy(p)
        body=self.body(p,ids);r=self.client.post(self.path(p)+'/preview',json=body)
        self.assertEqual(r.status_code,200,r.text);preview=r.json()
        self.assertTrue(preview['can_apply']);self.assertEqual(preview['summary']['assigned'],2)
        self.assertFalse(preview['summary']['complete'])
        self.assertEqual(len(preview['numbering_map']),47)
        self.assertEqual([r['new'] for r in preview['numbering_map'] if r['point_id'] in ids],
                         [10 if r['point_id']==ids[0] else 20 for r in preview['numbering_map'] if r['point_id'] in ids])
        current=self.client.get(f"/api/v1/projects/{p['id']}").json()
        self.assertEqual(current['nodes'],before['nodes']);self.assertEqual(current['version'],before['version'])
        r=self.client.post(self.path(p)+'/apply',json={**body,'preview_sha256':preview['preview_sha256']})
        self.assertEqual(r.status_code,200,r.text);p=r.json();nodes={n['id']:n for n in p['nodes']}
        self.assertEqual([nodes[uid]['number'] for uid in ids],[10,20])
        self.assertEqual(p['graph']['edges'],[{'from':ids[0],'to':ids[1],'line_id':nodes[ids[0]]['line_id'],'route':'main'}])
        self.assertTrue(all(n['station_mm'] is None and not n.get('coordinates_mm') for n in p['nodes']))
        for old in before['nodes']:
            node=nodes[old['id']]
            for key in ('id','instances','station_mm','evidence','source_observation','source_review_reasons'):
                self.assertEqual(node.get(key),old.get(key))
        self.assertTrue(all(nodes[uid]['topology_proof']['reviewed_by']=='local-engineer' for uid in ids))
        original_nodes=deepcopy(p['nodes']);history=deepcopy(p['numbering_history']);mapping=deepcopy(p['numbering_map'])
        repeat={'version':p['version'],'assignments':[],'reason':REASON,'confirmed':True}
        preview=self.client.post(self.path(p)+'/preview',json=repeat).json()
        self.assertTrue(preview['can_apply'])
        r=self.client.post(self.path(p)+'/apply',json={**repeat,'preview_sha256':preview['preview_sha256']})
        self.assertEqual(r.status_code,200,r.text);again=r.json()
        self.assertEqual(again['nodes'],original_nodes);self.assertEqual(again['numbering_history'],history)
        self.assertEqual(again['numbering_map'],mapping);self.assertFalse(again.get('review_approval'))

    def test_changed_preview_order_ambiguous_route_and_stale_versions_are_atomic(self):
        p,ids=self.source();p=self.inspect(p,ids);body=self.body(p,ids)
        preview=self.client.post(self.path(p)+'/preview',json=body).json()
        changed=deepcopy(body);changed['assignments'][1]['order']=2
        r=self.client.post(self.path(p)+'/apply',json={**changed,'preview_sha256':preview['preview_sha256']})
        self.assertEqual(r.status_code,422,r.text)
        changed['assignments'][1]['order']=0
        r=self.client.post(self.path(p)+'/preview',json=changed);self.assertEqual(r.status_code,200,r.text)
        ambiguous=r.json();self.assertFalse(ambiguous['can_apply'])
        self.assertIn('DUPLICATE_ROUTE_ORDER',{i['code'] for i in ambiguous['structural_issues']})
        r=self.client.post(self.path(p)+'/apply',json={**changed,'preview_sha256':ambiguous['preview_sha256']})
        self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}").json()['nodes'],p['nodes'])
        stale={**body,'version':p['version']-1}
        self.assertEqual(self.client.post(self.path(p)+'/preview',json=stale).status_code,409)
        self.assertEqual(self.client.post(self.path(p)+'/apply',json={**stale,'preview_sha256':preview['preview_sha256']}).status_code,409)
        duplicate=deepcopy(body);duplicate['assignments'].append(deepcopy(duplicate['assignments'][0]))
        self.assertEqual(self.client.post(self.path(p)+'/preview',json=duplicate).status_code,422)

    def test_nontee_takeoff_is_a_typed_exception_and_never_a_false_connection(self):
        p,ids=self.source();p=self.inspect(p,ids);body=self.body(p,ids)
        body['assignments'][1].update(route='branch-01',order=0,takeoff_id=ids[0])
        r=self.client.post(self.path(p)+'/preview',json=body);self.assertEqual(r.status_code,200,r.text)
        report=r.json();self.assertFalse(report['can_apply'])
        self.assertIn('BRANCH_TAKEOFF_INVALID',{i['code'] for i in report['structural_issues']})
        self.assertEqual(report['graph']['edges'],[])
        r=self.client.post(self.path(p)+'/apply',json={**body,'preview_sha256':report['preview_sha256']})
        self.assertEqual(r.status_code,422,r.text)

    def test_viewers_cannot_preview_or_apply_and_foreign_tenant_cannot_read(self):
        p,ids=self.source();p=self.inspect(p,ids);body=self.body(p,ids)
        preview=self.client.post(self.path(p)+'/preview',json=body).json()
        with fixture.main.db() as conn:conn.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertFalse(self.client.get(self.path(p)).json()['can_edit'])
        self.assertEqual(self.client.post(self.path(p)+'/preview',json=body).status_code,403)
        self.assertEqual(self.client.post(self.path(p)+'/apply',json={**body,'preview_sha256':preview['preview_sha256']}).status_code,403)
        with fixture.main.db() as conn:conn.execute('UPDATE projects SET tenant=? WHERE id=?',('foreign-tenant',p['id']))
        self.assertEqual(self.client.get(self.path(p)).status_code,404)
