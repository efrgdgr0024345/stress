from copy import deepcopy
from decimal import Decimal
import unittest
import io
from openpyxl import load_workbook
from services.api import main
from packages.physical.constraints import solve
from packages.physical.cod import proposals
from tests.integration import test_api as fixtures


class CodReconstructionTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload
    pdf=fixtures.ApiTests.pdf
    node=fixtures.ApiTests.node

    def model(self):
        p=self.upload(self.create())
        for order in range(5):
            body=self.node(p,'','SYNTHETIC explicit engineering point, route station unknown')
            body.update(kind='elbow' if order==2 else 'endpoint',order=order)
            body['instances'][0]['anchor']=[60+order*90,200]
            body['instances'][0]['bubble']=[60+order*90,150]
            r=self.client.post(f"/api/v1/projects/{p['id']}/nodes",json=body)
            self.assertEqual(r.status_code,200,r.text);p=r.json()
        r=self.client.post(f"/api/v1/projects/{p['id']}/materials",json={'version':p['version'],'sheet_id':p['sheets'][0]['id'],
            'item_no':'1','family':'elbow','description':'SYNTHETIC 90 DEG elbow','size':'8','quantity':1,'observed':0,'evidence':'SYNTHETIC original component inventory'})
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        for index,point in [(0,[0,0,0]),(1,[100,0,0]),(3,[200,100,0]),(4,[200,200,0])]:
            for axis,value in zip(('X','Y','Z'),point):
                r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/dimensions",json={'version':p['version'],'kind':'COORDINATE','axis':axis,
                    'from_point_id':p['nodes'][index]['id'],'to_point_id':None,'source_text':str(value)+' mm','tolerance_text':'0 mm',
                    'sheet_id':p['sheets'][0]['id'],'evidence':'SYNTHETIC independent source centreline leg coordinate','confirmed':True})
                self.assertEqual(r.status_code,200,r.text);p=r.json()
        component=self.client.get(f"/api/v1/projects/{p['id']}/physical-model").json()['components'][0]
        n=p['nodes'][2];x,y=n['instances'][0]['anchor']
        body={'version':p['version'],'kind':'elbow','ports':{'theoretical_cod':{'point_id':n['id'],'sheet_id':p['sheets'][0]['id'],
            'bbox':[x-5,y-5,x+5,y+5],'evidence':'SYNTHETIC source dimension chain locates theoretical centreline intersection',
            'dimension_convention':'The source convention defines COD as intersection of the two straight centreline legs.'}},
            'cod_convention_confirmed':True,'evidence':'SYNTHETIC explicit theoretical COD source convention','confirmed':True}
        r=self.client.patch(f"/api/v1/projects/{p['id']}/physical-model/components/{component['id']}",json=body)
        self.assertEqual(r.status_code,200,r.text)
        return r.json(),component['id']

    def accept(self,p,component):
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/components/{component}/accept-cod",json={'version':p['version'],
            'reason':'SYNTHETIC inspected exact independent source-leg intersection and dimension convention','confirmed':True})
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def test_exact_cod_is_reviewed_without_creating_station_or_bend_radius(self):
        p,component=self.model();before=deepcopy(p);p=self.accept(p,component)
        cod=next(c for c in solve(p)['coordinates'] if c['point_id']==p['nodes'][2]['id'])
        self.assertEqual({k:v['value_mm'] for k,v in cod['axes'].items()},{'X':'200','Y':'0','Z':'0'})
        self.assertTrue(all(n['station_mm'] is None for n in p['nodes']))
        self.assertEqual([n['instances'] for n in p['nodes']],[n['instances'] for n in before['nodes']])
        self.assertEqual(len(p['physical_model']['constraints']),15)
        self.assertEqual(proposals(p)[0]['status'],'COD_ACCEPTED')
        self.assertIsNone(proposals(p)[0]['radius_mm'])
        self.assertTrue(all(c['source_text'] for c in p['physical_model']['constraints']))
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/apply-vectors",json={'version':p['version'],
            'reason':'SYNTHETIC accepted exact signed source vectors after proved COD','confirmed':True})
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        r=self.client.get(f"/api/v1/projects/{p['id']}/results/workbook")
        self.assertEqual(r.status_code,200,r.text[:200] if r.status_code!=200 else '')
        book=load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
        self.assertEqual(book['Bend COD']['C6'].value,200)
        self.assertIsNone(book['Bend COD']['F6'].value);self.assertIsNone(book['Bend COD']['G6'].value)
        self.assertEqual(book['CAESAR input']['E6'].value,100)
        self.assertEqual(book['Coordinates'].max_row,20);book.close()

    def test_source_change_invalidates_derivation_and_requires_new_acceptance(self):
        p,component=self.model();p=self.accept(p,component)
        c=next(c for c in p['physical_model']['constraints'] if c['from_point_id']==p['nodes'][3]['id'] and c['axis']=='X')
        body={k:c.get(k) for k in ('kind','axis','from_point_id','to_point_id','source_text','tolerance_text','sheet_id','evidence')}
        body.update(version=p['version'],source_text='220 mm',evidence='SYNTHETIC explicitly corrected engineering source coordinate',confirmed=True)
        r=self.client.patch(f"/api/v1/projects/{p['id']}/physical-model/dimensions/{c['id']}",json=body)
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        self.assertIn('COD_SOURCE_STALE',p['nodes'][2]['reasons'])
        cod=next(c for c in solve(p)['coordinates'] if c['point_id']==p['nodes'][2]['id'])
        self.assertTrue(all(v['value_mm'] is None for v in cod['axes'].values()))
        self.assertEqual(proposals(p)[0]['coordinates_mm']['X'],'240')
        p=self.accept(p,component)
        self.assertEqual(len(p['physical_model']['constraints']),15)
        self.assertNotIn('COD_SOURCE_STALE',p['nodes'][2]['reasons'])

    def test_independent_cod_coordinate_conflict_blocks_acceptance_atomically(self):
        p,component=self.model()
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/dimensions",json={
            'version':p['version'],'kind':'COORDINATE','axis':'X','from_point_id':p['nodes'][2]['id'],
            'source_text':'250 mm','tolerance_text':'0 mm','sheet_id':p['sheets'][0]['id'],
            'evidence':'SYNTHETIC independently accepted source COD coordinate conflicting with leg intersection','confirmed':True})
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        self.assertEqual(proposals(p)[0]['status'],'COD_CONFLICTS_WITH_ACCEPTED_SOURCE')
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/components/{component}/accept-cod",json={
            'version':p['version'],'reason':'SYNTHETIC attempted acceptance despite independent source conflict','confirmed':True})
        self.assertEqual(r.status_code,409,r.text)
        after=self.client.get(f"/api/v1/projects/{p['id']}").json()
        self.assertEqual(after['version'],p['version'])
        self.assertFalse(any(c.get('cod_derivation') for c in after['physical_model']['constraints']))
