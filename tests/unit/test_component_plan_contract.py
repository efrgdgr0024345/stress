"""Explicit plan rules on labelled synthetic inputs; not the 1010 golden suite."""
from copy import deepcopy
from decimal import Decimal
import unittest
from packages.engineering import compute_reasons,dimension_mm,renumber,topology
from packages.physical import prepare,audit
from tests.unit.test_physical_model import project,node,material,mapped


class ComponentPlanContractTests(unittest.TestCase):
    def test_flange_face_and_dot_need_distinct_stations_and_distinct_source_proof(self):
        p=project();p['materials']=[material('f','flange')]
        p['nodes']=[node('face','0',kind='flange'),node('dot','100',kind='flange')]
        c=prepare(p)['components'][0];mapped(p,c,['face','dot'])
        self.assertEqual(audit(p)['issues'],[])
        c['ports']['opposite_pipe_dot']['proof']['kind']='FLANGE_FACE'
        self.assertIn('UNKNOWN_FLANGE_END',{i['code'] for i in audit(p)['issues']})

    def test_main_and_branch_use_one_tee_identity(self):
        p=project();p['materials']=[material('t','tee')]
        p['nodes']=[node('start','0'),node('tee','100',kind='tee',order=1),node('end','200',order=2),node('branch','50',route='branch-01')]
        p['nodes'][-1]['takeoff_id']='tee'
        mapped(p,prepare(p)['components'][0],['tee']);renumber(p['nodes'])
        self.assertEqual(audit(p)['issues'],[])
        graph=topology(p['nodes']);self.assertEqual(graph['points'].count('tee'),1)
        self.assertTrue(any(e['from']=='tee' and e['to']=='branch' for e in graph['edges']))
        self.assertEqual(next(n for n in p['nodes'] if n['id']=='tee')['number'],20)

    def test_paper_bend_alone_does_not_prove_theoretical_cod(self):
        p=project();p['materials']=[material('e','elbow')];p['nodes']=[node('cod','100',kind='elbow')]
        c=prepare(p)['components'][0];mapped(p,c,['cod'])
        del c['ports']['theoretical_cod']['proof']['dimension_convention']
        before=audit(p)['issues'];self.assertIn('UNCONFIRMED_ELBOW_COD',{i['code'] for i in before})
        p['nodes'][0]['instances'][0]['anchor']=[55,45]
        self.assertEqual(audit(p)['issues'],before)

    def test_inline_instrument_shares_a_flange_face_but_pit_has_one_process_end(self):
        p=project();p['materials']=[material('f','flange'),material('i','instrument','INLINE FLOWMETER'),material('pit','instrument','PIT')]
        p['nodes']=[node('dot','0'),node('shared','20'),node('out','220'),node('pit-end','300')]
        components=prepare(p)['components']
        for c,ends in zip(components,[['shared','dot'],['shared','out'],['pit-end']]):mapped(p,c,ends)
        result=audit(p);self.assertEqual(result['issues'],[])
        self.assertEqual(len(result['associations']['shared']),2)
        self.assertEqual(len(components[-1]['ports']),1)
        self.assertEqual(len(p['nodes']),4)

    def test_historic_support_gaps_use_accepted_along_route_stations(self):
        for source,expected in [('2 in',Decimal('50.8')),('0.5 in',Decimal('12.7')),('2 1/8 in',Decimal('53.975')),('6 in',Decimal('152.4'))]:
            with self.subTest(source=source):
                p=project();p['nodes']=[node('up','1000',kind='support'),node('down',str(1000+dimension_mm(source)),kind='support',order=1)]
                p['nodes'][0]['instances'][0]['anchor']=[10,10];p['nodes'][1]['instances'][0]['anchor']=[590,490]
                compute_reasons(p['nodes'])
                self.assertNotIn('SUPPORT_WITHIN_6_IN',p['nodes'][0]['reasons'])
                self.assertIn('SUPPORT_WITHIN_6_IN',p['nodes'][1]['reasons'])
                self.assertEqual(Decimal(p['nodes'][1]['support_gap_mm']),expected)
                saved=deepcopy(p['nodes']);renumber(p['nodes']);compute_reasons(p['nodes'])
                for old,new in zip(saved,p['nodes']):
                    for field in ('id','station_mm','evidence','reasons'):self.assertEqual(old[field],new[field])

    def test_nearby_supports_on_different_routes_or_unknown_stations_are_not_merged(self):
        p=project();p['nodes']=[node('a','0',kind='support'),node('b',None,kind='support',order=1),node('c','1',kind='support',route='branch-01')]
        compute_reasons(p['nodes'])
        self.assertTrue(all('SUPPORT_WITHIN_6_IN' not in n['reasons'] for n in p['nodes']))
        self.assertEqual(len({n['id'] for n in p['nodes']}),3)
        self.assertIn('UNVERIFIED_DIMENSION',p['nodes'][1]['reasons'])

    def test_one_continuation_uuid_repeats_number_and_reasons_on_two_sheets(self):
        n=node('common',None,kind='continuation')
        n['instances'].append({'sheet_id':'sheet-b','anchor':[180,260],'bubble':[210,230]})
        nodes=[n];renumber(nodes);compute_reasons(nodes)
        self.assertEqual(len(nodes),1);self.assertEqual(n['number'],10)
        self.assertEqual(len(n['instances']),2);self.assertIn('UNVERIFIED_DIMENSION',n['reasons'])
        self.assertNotIn('PROVISIONAL_CONTINUATION',n['reasons'])

    def test_unlocated_required_features_create_exceptions_not_stations(self):
        p=project();p['materials']=[material('v','valve'),material('f','flange'),material('s','support')]
        prepare(p);result=audit(p)
        self.assertEqual(p['nodes'],[])
        self.assertTrue({'UNKNOWN_VALVE_END','UNKNOWN_FLANGE_END','UNKNOWN_SUPPORT_STATION'}<={i['code'] for i in result['issues']})

    def test_all_topology_elements_stay_in_review_tables_when_native_export_is_blocked(self):
        from tests.unit.test_neutral_export import model
        from packages.workbooks import tables
        from packages.workbooks.caesar_neutral import assess
        from packages.automation.recognize import identity
        p=model();p['nodes']=[];p['analysis_model']={}
        for index,kind in enumerate(('endpoint','tee','elbow','flange','support','endpoint')):
            n=node(f'p{index}',None,kind=kind,order=index,route='main' if index<4 else 'branch-01')
            if index>=4:n['takeoff_id']='p1'
            p['nodes'].append(n)
        renumber(p['nodes'])
        expected=topology(p['nodes'])['edges']
        self.assertFalse(assess(p)['available'])
        actual=next(t['rows'] for t in tables(p) if t['name']=='CAESAR input')
        self.assertEqual(len(expected),5);self.assertEqual(len(actual),5)
        self.assertEqual({r['id'] for r in actual},{identity(p['id'],e['from'],e['to']) for e in expected})
        self.assertTrue(all(r['dx'] is None and r['dy'] is None and r['dz'] is None for r in actual))
