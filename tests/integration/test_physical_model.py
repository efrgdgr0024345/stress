"""Real source-bound interface/dimension APIs and model review invalidation."""
from copy import deepcopy
import io
import json
import unittest
from decimal import Decimal
from openpyxl import load_workbook
from services.api import main
from packages.physical.constraints import solve
from tests.integration import test_api as fixtures


class PhysicalModelTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    pdf=fixtures.ApiTests.pdf
    upload=fixtures.ApiTests.upload
    node=fixtures.ApiTests.node

    def points(self,count=3):
        p=self.upload(self.create())
        for order in range(count):
            body=self.node(p,f'{order*100} mm','Explicit synthetic source station evidence')
            body.update(order=order,kind='endpoint')
            body['instances'][0].update(anchor=[70+order*100,180],bubble=[70+order*100,140])
            r=self.client.post(f"/api/v1/projects/{p['id']}/nodes",json=body)
            self.assertEqual(r.status_code,200,r.text);p=r.json()
        return p

    def state(self,p):
        r=self.client.get(f"/api/v1/projects/{p['id']}/physical-model")
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def add(self,p,a,b,value,axis='X',kind='DELTA',tolerance='0 mm'):
        body={'version':p['version'],'kind':kind,'axis':axis,'from_point_id':a,'to_point_id':b,
              'source_text':value,'tolerance_text':tolerance,'sheet_id':p['sheets'][0]['id'],
              'evidence':'Explicit synthetic source engineering dimension','confirmed':True}
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/dimensions",json=body)
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def material(self,p,family='flange',description='SYNTHETIC WN flange',count=1):
        r=self.client.post(f"/api/v1/projects/{p['id']}/materials",json={
            'version':p['version'],'sheet_id':p['sheets'][0]['id'],'item_no':'1','family':family,
            'description':description,'size':'8','quantity':count,'observed':0,
            'evidence':'Synthetic source materials list'})
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def port(self,p,point):
        x,y=point['instances'][0]['anchor']
        return {'point_id':point['id'],'sheet_id':p['sheets'][0]['id'],'bbox':[x-8,y-8,x+8,y+8],
                'evidence':'Confirmed synthetic source flange face or opposite black dot'}

    def test_flange_source_face_and_opposite_dot_are_distinct_and_counted(self):
        p=self.material(self.points(2));component=self.state(p)['components'][0]
        path=f"/api/v1/projects/{p['id']}/physical-model/components/{component['id']}"
        body={'version':p['version'],'kind':'flange','ports':{'flange_face':self.port(p,p['nodes'][0]),'opposite_pipe_dot':self.port(p,p['nodes'][0])},'evidence':'Synthetic face versus opposite black dot source association','confirmed':True}
        self.assertEqual(self.client.patch(path,json=body).status_code,422)
        body['ports']['opposite_pipe_dot']=self.port(p,p['nodes'][1])
        bad=deepcopy(body);bad['ports']['opposite_pipe_dot']['bbox']=[10,10,20,20]
        self.assertEqual(self.client.patch(path,json=bad).status_code,422)
        r=self.client.patch(path,json=body);self.assertEqual(r.status_code,200,r.text);p=r.json()
        self.assertEqual(p['materials'][0]['observed'],1)
        self.assertEqual(self.state(p)['issues'],[])
        self.assertEqual(p['physical_model']['components'][0]['ports']['opposite_pipe_dot']['proof']['kind'],'BLACK_DOT')
        self.assertTrue(all(n['component_ports'] for n in p['nodes']))
        # Moving the presentation bubble keeps the source proof; moving its
        # anchor away from the inspected feature requires association review.
        node=p['nodes'][0];edit=self.node(p,'0 mm',node['evidence']);edit.update(kind='endpoint',order=0,instances=deepcopy(node['instances']))
        edit['instances'][0]['bubble']=[90,90]
        p=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{node['id']}",json=edit).json()
        self.assertEqual(self.state(p)['issues'],[])
        edit['version']=p['version'];edit['instances'][0]['anchor']=[300,300]
        p=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{node['id']}",json=edit).json()
        self.assertIn('UNKNOWN_FLANGE_END',{i['code'] for i in self.state(p)['issues']})
        self.assertIn('UNKNOWN_FLANGE_END',p['nodes'][0]['reasons'])

    def test_pit_forbids_an_unsupported_second_connection_and_shared_supports_reuse_points(self):
        p=self.material(self.points(1),'instrument','SYNTHETIC PIT single connection')
        component=self.state(p)['components'][0]
        self.assertEqual(component['kind'],'single_instrument')
        body={'version':p['version'],'kind':'single_instrument','ports':{'process_connection':self.port(p,p['nodes'][0]),'second_end':self.port(p,p['nodes'][0])},'evidence':'Synthetic single-ended process connection','confirmed':True}
        self.assertEqual(self.client.patch(f"/api/v1/projects/{p['id']}/physical-model/components/{component['id']}",json=body).status_code,422)
        p=self.material(self.points(1),'support','SYNTHETIC coincident support tags',2)
        for component in self.state(p)['components']:
            body={'version':p['version'],'kind':'support','ports':{'support_station':self.port(p,p['nodes'][0])},'evidence':'Two source support tags genuinely coincide at one physical station','confirmed':True}
            r=self.client.patch(f"/api/v1/projects/{p['id']}/physical-model/components/{component['id']}",json=body)
            self.assertEqual(r.status_code,200,r.text);p=r.json()
        self.assertEqual(len(p['nodes']),1);self.assertEqual(len(p['nodes'][0]['component_ports']),2)
        self.assertEqual(p['materials'][0]['observed'],2)

    def test_exact_signed_chains_preserve_unknown_axes_and_never_modify_stations(self):
        p=self.points();a,b,c=[n['id'] for n in p['nodes']]
        stations=[n['station_mm'] for n in p['nodes']]
        p=self.add(p,a,None,'1000 mm',kind='COORDINATE')
        p=self.add(p,a,b,'6 in');p=self.add(p,b,c,'-2 1/8 in')
        solution=self.state(p)['solution']
        last=next(n for n in solution['coordinates'] if n['point_id']==c)
        self.assertEqual(Decimal(last['axes']['X']['value_mm']),Decimal('1098.425'))
        self.assertEqual(last['axes']['Y']['value_mm'],None)
        self.assertEqual([n['station_mm'] for n in p['nodes']],stations)
        first=p['physical_model']['constraints'][1]
        self.assertEqual(first['source_text'],'6 in');self.assertEqual(first['value_mm'],'152.4')

    def test_complete_vectors_are_accepted_explicitly_and_change_requires_fresh_acceptance(self):
        p=self.points(2);a,b=[n['id'] for n in p['nodes']]
        for axis,value in [('X','100 mm'),('Y','0 mm'),('Z','0 mm')]:p=self.add(p,a,b,value,axis)
        path=f"/api/v1/projects/{p['id']}/physical-model/apply-vectors"
        r=self.client.post(path,json={'version':p['version'],'reason':'Accepted synthetic signed engineering XYZ proof','confirmed':True})
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        element=p['analysis_model']['elements'][0]
        self.assertEqual((element['dx_mm'],element['dy_mm'],element['dz_mm']),('100','0','0'))
        self.assertFalse(self.state(p)['solution']['issues'])
        original=self.state(p)['solution']['input_sha256']
        constraint=next(c for c in p['physical_model']['constraints'] if c['axis']=='X')
        body={k:constraint[k] for k in ('kind','axis','from_point_id','to_point_id','sheet_id','evidence','tolerance_text')}
        body.update(version=p['version'],source_text='-100 mm',confirmed=True)
        r=self.client.patch(f"/api/v1/projects/{p['id']}/physical-model/dimensions/{constraint['id']}",json=body)
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        self.assertNotEqual(self.state(p)['solution']['input_sha256'],original)
        self.assertIn('DIMENSION_SOLUTION_STALE',{i['code'] for i in p['issues']})
        self.assertFalse(self.client.get(f"/api/v1/projects/{p['id']}/results").json()['native']['available'])
        r=self.client.post(path,json={'version':p['version'],'reason':'Accepted revised synthetic signed XYZ proof','confirmed':True})
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        self.assertEqual(p['analysis_model']['elements'][0]['dx_mm'],'-100')
        self.assertNotIn('DIMENSION_SOLUTION_STALE',{i['code'] for i in p['issues']})

    def test_conflicts_permissions_retired_points_and_version_fences(self):
        p=self.points(2);a,b=[n['id'] for n in p['nodes']]
        p=self.add(p,a,b,'100 mm');p=self.add(p,a,b,'101 mm')
        self.assertIn('COORDINATE_MISMATCH',{i['code'] for i in p['issues']})
        path=f"/api/v1/projects/{p['id']}/physical-model/apply-vectors"
        decision={'version':p['version'],'reason':'Cannot accept conflicting dimensional proof','confirmed':True}
        self.assertEqual(self.client.post(path,json=decision).status_code,409)
        with main.db() as conn:conn.execute("UPDATE users SET role='reviewer' WHERE id='local-engineer'")
        self.assertEqual(self.client.post(path,json=decision).status_code,403)
        with main.db() as conn:conn.execute("UPDATE projects SET tenant='other' WHERE id=?",(p['id'],))
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}/physical-model").status_code,404)

    def test_delete_source_dimension_body_is_bounded_before_json_parsing(self):
        p=self.points(1);version=p['version']
        response=self.client.request('DELETE',f"/api/v1/projects/{p['id']}/physical-model/dimensions/{main.uid()}",
            content=b'{"reason":"'+b'x'*(3*1024*1024)+b'"}',headers={'Content-Type':'application/json'})
        self.assertEqual(response.status_code,413)
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}").json()['version'],version)
