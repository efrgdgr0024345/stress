from copy import deepcopy
from decimal import Decimal
import unittest
from packages.engineering.continuations import assess_pair,candidate_matches,source_candidates,size_value,merge_identity
from packages.physical.constraints import solve
from tests.unit.test_physical_model import project,node,dimension


def fixture(delta='0'):
    p=project();p['sheets'][0].update(sha256='a'*64,identity_verified=True,printed_id='SHEET 1 OF 2')
    p['sheets'].append({**p['sheets'][0],'id':'sheet-b','printed_id':'SHEET 2 OF 2','content_hash':['b'*64]})
    p['nodes']=[node('left','100'),node('right','100',order=1)]
    p['nodes'][1]['instances'][0]['sheet_id']='sheet-b'
    p['physical_model']={'components':[],'constraints':[]}
    for point,sheet,offset in [('left','sheet-a',Decimal(0)),('right','sheet-b',Decimal(delta))]:
        for axis,value in [('X',Decimal(1000)+offset),('Y',Decimal(-500)),('Z',Decimal(300))]:
            d=dimension(point+axis,point,None,str(value),axis=axis,kind='COORDINATE')
            d.update(sheet_id=sheet,source_content_hash=['a'*64] if sheet=='sheet-a' else ['b'*64])
            p['physical_model']['constraints'].append(d)
    return p


class ContinuationTests(unittest.TestCase):
    def test_per_axis_one_inch_threshold_and_tolerance_are_inclusive(self):
        for delta,status in [('0','EXACT_COORDINATE_MATCH'),('0.005','WITHIN_TOLERANCE_REVIEW'),
                ('0.02','COORDINATE_DISCREPANCY'),('25.399','COORDINATE_DISCREPANCY'),
                ('25.4','MATCH_TO_BE_CONFIRMED_BY_ENGINEER'),('-25.4','MATCH_TO_BE_CONFIRMED_BY_ENGINEER')]:
            p=fixture(delta);before=deepcopy(p)
            with self.subTest(delta=delta):
                result=assess_pair(p,'left','right','8 in','8')
                self.assertEqual(result['status'],status);self.assertEqual(Decimal(result['delta_mm']['X']),Decimal(delta))
                self.assertEqual(Decimal(result['delta_mm']['Y']),0);self.assertEqual(p,before)

    def test_missing_axis_size_line_or_sheet_evidence_cannot_be_exact(self):
        p=fixture();p['physical_model']['constraints'].pop()
        self.assertEqual(assess_pair(p,'left','right','8','8')['status'],'COORDINATE_EVIDENCE_REQUIRED')
        self.assertEqual(assess_pair(fixture(),'left','right','8','2')['status'],'REJECTED_SIZE_MISMATCH')
        p=fixture();p['nodes'][1]['line_id']='OTHER'
        with self.assertRaises(ValueError):assess_pair(p,'left','right','8','8')
        p=fixture();p['nodes'][1]['instances'][0]['sheet_id']='sheet-a'
        with self.assertRaises(ValueError):assess_pair(p,'left','right','8','8')
        for text in ('unknown','8 mm','8x2','0','8 px'):
            with self.subTest(text=text),self.assertRaises(ValueError):size_value(text)

    def test_independent_absolute_anchors_produce_signed_element_vectors(self):
        p=fixture('100');p['nodes'][1]['station_mm']='200'
        result=solve(p)
        self.assertEqual(result['elements'][0]['delta_mm'],{'X':'100','Y':'0','Z':'0'})
        self.assertEqual(len(result['elements'][0]['evidence_groups']['X']),2)
        self.assertFalse(result['issues'])
        p['nodes'][0]['instances'][0]['anchor']=[100,400]
        self.assertEqual(solve(p),result)

    def test_nonadjacent_equal_coordinates_do_not_silently_remove_a_route_loop(self):
        p=fixture();p['nodes'][1]['order']=2
        p['nodes'].append(node('intermediate','150',order=1))
        before=deepcopy(p)
        with self.assertRaisesRegex(ValueError,'loop'):merge_identity(p,'left','right')
        self.assertEqual(p,before)

    def test_reference_search_uses_printed_sheet_identity_never_page_index(self):
        p=fixture();a,b=p['sheets']
        candidates=[{'id':'a','sheet_id':a['id'],'line_id':'LINE-A','target_printed_sheet':2,'target_line_proposal':None},
                    {'id':'b','sheet_id':b['id'],'line_id':'LINE-A','target_printed_sheet':1,'target_line_proposal':None}]
        self.assertEqual(len(candidate_matches(candidates,p['sheets'])),1)
        a['printed_id']='Unidentified';a['page_index']=0
        self.assertEqual(candidate_matches(candidates,p['sheets']),[])

    def test_source_words_only_prepare_proposals(self):
        p=fixture();page={'words':[{'text':'CONT.','bbox':[20,20,55,30],'confidence':1,'method':'native','evidence_id':'a'},
            {'text':'ON','bbox':[60,20,75,30],'confidence':1,'method':'native','evidence_id':'b'},
            {'text':'SHEET','bbox':[80,20,120,30],'confidence':1,'method':'native','evidence_id':'c'},
            {'text':'2','bbox':[125,20,135,30],'confidence':1,'method':'native','evidence_id':'d'}]}
        proposals=source_candidates(page,p['sheets'][0])
        self.assertEqual(len(proposals),1);self.assertEqual(proposals[0]['target_printed_sheet'],2)
        self.assertEqual(proposals[0]['verification'],'proposed');self.assertNotIn('station_mm',proposals[0])
        page['words'].append({'text':'UNRELATED MATERIAL TABLE','bbox':[900,20,1200,30],'confidence':1,'method':'native','evidence_id':'e'})
        self.assertEqual(source_candidates(page,p['sheets'][0])[0]['source_text'],proposals[0]['source_text'])
