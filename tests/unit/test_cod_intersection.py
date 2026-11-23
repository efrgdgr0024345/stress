from copy import deepcopy
from decimal import Decimal
import unittest
from packages.physical.cod import intersect_legs,proposals,CONVENTION
from packages.physical import prepare
from tests.unit.test_physical_model import project,node,material,mapped,dimension


def fixture():
    p=project();p['sheets'][0]['sha256']='a'*64
    p['nodes']=[node(str(i),None,kind='elbow' if i==2 else 'endpoint',order=i) for i in range(5)]
    p['materials']=[material('bend','elbow','SYNTHETIC 90 DEG ELBOW')]
    c=prepare(p)['components'][0];mapped(p,c,['2'])
    c['ports']['theoretical_cod']['proof']['dimension_convention_kind']=CONVENTION
    p['physical_model']['constraints']=[]
    for uid,point in [('0',[0,0,0]),('1',[100,0,0]),('3',[200,100,0]),('4',[200,200,0])]:
        for axis,value in zip(('X','Y','Z'),point):p['physical_model']['constraints'].append(dimension(uid+axis,uid,None,str(value),axis=axis,kind='COORDINATE'))
    return p


class CodIntersectionTests(unittest.TestCase):
    def test_exact_proved_3d_legs_give_theoretical_cod_not_a_paper_bend(self):
        for points,expected in [([[0,0,0],[100,0,0],[200,100,0],[200,200,0]],{'X':'200','Y':'0','Z':'0'}),
            ([[0,0,0],[100,0,0],[300,100,100],[400,200,200]],{'X':'200','Y':'0','Z':'0'})]:
            result=intersect_legs(points);self.assertEqual(result['status'],'COD_PROPOSED')
            self.assertEqual(result['coordinates_mm'],expected)

    def test_parallel_skew_and_wrong_extension_orientation_stay_unknown(self):
        for points,status in [([[0,0,0],[100,0,0],[200,0,0],[300,0,0]],'COD_NOT_UNIQUELY_CONSTRAINED'),
            ([[0,0,0],[100,0,0],[200,100,1],[200,200,1]],'COD_LEG_COORDINATES_CONFLICT'),
            ([[0,0,0],[100,0,0],[50,100,0],[50,200,0]],'COD_TANGENT_ORIENTATION_REVIEW')]:
            result=intersect_legs(points);self.assertEqual(result['status'],status);self.assertIsNone(result['coordinates_mm'])
        result=intersect_legs([[0,0,0],['0.1',0,0],[0,1,0],[-1,4,0]])
        self.assertEqual(result['status'],'COD_EXACT_PRECISION_REVIEW');self.assertIsNone(result['coordinates_mm'])
        self.assertEqual(result['exact_rational_mm'][0],'1/3')

    def test_source_convention_and_all_engineering_axes_are_required(self):
        p=fixture();before=deepcopy(p)
        result=proposals(p)[0];self.assertEqual(result['status'],'COD_PROPOSED')
        self.assertEqual(result['coordinates_mm'],{'X':'200','Y':'0','Z':'0'})
        self.assertIsNone(result['station_mm']);self.assertIsNone(result['radius_mm']);self.assertFalse(result['drawing_pixels_used'])
        self.assertEqual(p,before)
        reversed_source=deepcopy(p)
        for n in reversed_source['nodes']:n['order']=4-n['order']
        self.assertEqual(proposals(reversed_source)[0]['coordinates_mm'],result['coordinates_mm'])
        p['physical_model']['constraints'].pop()
        self.assertEqual(proposals(p)[0]['status'],'COD_COORDINATE_EVIDENCE_REQUIRED')
        p=fixture();p['physical_model']['components'][0]['ports']['theoretical_cod']['proof'].pop('dimension_convention_kind')
        self.assertEqual(proposals(p)[0]['status'],'COD_SOURCE_CONVENTION_REQUIRED')
