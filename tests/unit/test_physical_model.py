"""Original component/interface rules and signed dimensional chains."""
from copy import deepcopy
from decimal import Decimal
import unittest
from packages.physical import requirements,prepare,audit,POLICIES
from packages.physical.constraints import solve


def project():
    return {'id':'physical-fixture','line_id':'LINE-A','sheets':[{'id':'sheet-a','line_id':'LINE-A','content_hash':['a'*64],'width':600,'height':500}],
            'nodes':[],'materials':[]}


def node(uid,station='0',kind='endpoint',route='main',order=0):
    return {'id':uid,'line_id':'LINE-A','kind':kind,'route':route,'order':order,'station_mm':station,
            'evidence':'Explicit synthetic source dimension','verification':'reviewed','instances':[{'sheet_id':'sheet-a','anchor':[50,50],'bubble':[100,50]}]}


def material(uid,family,description='',quantity=1):
    return {'id':uid,'family':family,'description':description,'quantity':quantity,
            'quantity_unit':'count','item_no':uid,'sheet_id':'sheet-a','size':'8'}


def mapped(p,component,points):
    component['verification']='reviewed';component['evidence']='Synthetic source association'
    for key,proof,point in zip(POLICIES[component['kind']]['ports'],POLICIES[component['kind']]['proof'],points):
        component['ports'][key]={'point_id':point,'proof':{'sheet_id':'sheet-a','content_hash':['a'*64],
            'kind':proof,'bbox':[40,40,60,60],'evidence':'Inspected synthetic source feature','dimension_convention':'Explicit theoretical centreline intersection'}}


def dimension(uid,a,b,value,axis='X',kind='DELTA',tolerance='0'):
    return {'id':uid,'kind':kind,'axis':axis,'from_point_id':a,'to_point_id':b,'value_mm':value,
            'source_text':value+' mm','tolerance_mm':tolerance,'evidence':'Synthetic printed dimension chain',
            'verification':'reviewed'}


class PhysicalComponentTests(unittest.TestCase):
    def test_component_policy_counts_do_not_create_unproved_points(self):
        p=project()
        for key,family,text in [('f','flange','WN FLANGE'),('v','valve','BALL VALVE'),('i','instrument','INLINE FLOWMETER'),('pit','instrument','PIT'),('t','tee','TEE'),('e','elbow','ELBOW'),('s','support','SUPPORT')]:
            p['materials'].append(material(key,family,text))
        result=prepare(p)
        self.assertEqual([len(c['ports']) for c in result['components']],[2,2,2,1,1,1,1])
        self.assertEqual(p['nodes'],[])
        self.assertTrue(audit(p)['issues'])
        saved=deepcopy(p);prepare(p)
        self.assertEqual(p,saved)

    def test_adjacent_valve_and_flange_reuse_the_same_interface_uuid(self):
        p=project();p['materials']=[material('f','flange'),material('v','valve')]
        p['nodes']=[node('dot','0'),node('face','20'),node('valve-end','220')]
        model=prepare(p);mapped(p,model['components'][0],['face','dot']);mapped(p,model['components'][1],['face','valve-end']);prepare(p)
        result=audit(p)
        self.assertEqual(result['issues'],[])
        self.assertEqual(len(p['nodes']),3)
        self.assertEqual(len(result['associations']['face']),2)
        self.assertEqual(len(p['nodes'][1]['component_ports']),2)

    def test_both_flange_ends_at_face_or_equal_station_are_rejected(self):
        p=project();p['materials']=[material('f','flange')];p['nodes']=[node('a','20'),node('b','20.0')]
        component=prepare(p)['components'][0];mapped(p,component,['a','a'])
        self.assertIn('COMPONENT_ENDS_COINCIDENT',{i['code'] for i in audit(p)['issues']})
        mapped(p,component,['a','b'])
        self.assertIn('COMPONENT_ENDS_COINCIDENT',{i['code'] for i in audit(p)['issues']})
        p['nodes'][1]['station_mm']='21';component['ports']['opposite_pipe_dot']['proof']['kind']='FLANGE_FACE'
        self.assertIn('UNKNOWN_FLANGE_END',{i['code'] for i in audit(p)['issues']})

    def test_tee_main_series_elbow_cod_and_unknown_instrument_are_explicit(self):
        p=project();p['materials']=[material('t','tee'),material('e','elbow'),material('i','instrument','INSTRUMENT')]
        p['nodes']=[node('t','0',kind='tee',route='branch-01'),node('e','100',kind='elbow')]
        model=prepare(p);mapped(p,model['components'][0],['t']);mapped(p,model['components'][1],['e'])
        model['components'][1]['ports']['theoretical_cod']['proof'].pop('dimension_convention')
        codes={i['code'] for i in audit(p)['issues']}
        self.assertTrue({'TEE_INTERSECTION_UNCONFIRMED','UNCONFIRMED_ELBOW_COD','INSTRUMENT_CONNECTION_TYPE_UNCONFIRMED'}<=codes)

    def test_same_support_station_may_have_multiple_distinct_support_associations(self):
        p=project();p['materials']=[material('s','support',quantity=2)];p['nodes']=[node('shared','100',kind='support')]
        model=prepare(p)
        for c in model['components']:mapped(p,c,['shared'])
        result=audit(p)
        self.assertFalse(result['issues']);self.assertEqual(len(result['associations']['shared']),2)
        self.assertEqual(len(p['nodes']),1)

    def test_stale_source_classification_unknown_count_and_caps_are_reported(self):
        p=project();p['materials']=[material('pit','instrument','PIT')];p['nodes']=[node('a')]
        mapped(p,prepare(p)['components'][0],['a']);prepare(p)
        p['materials'][0]['description']='INLINE FLOWMETER'
        model=prepare(p)
        self.assertEqual(len(model['components'][0]['ports']),2)
        self.assertEqual(model['components'][0]['verification'],'proposed')
        self.assertEqual(len(model['retired_components']),1)
        p['materials']=[material('unknown','flange',quantity=None),material('many','valve',quantity=1001)]
        result=audit(p)
        self.assertEqual(result['components'],[])
        self.assertEqual({i['code'] for i in result['issues']},{'COMPONENT_QUANTITY_UNRESOLVED','COMPONENT_OCCURRENCE_LIMIT'})


class DimensionalConstraintTests(unittest.TestCase):
    def model(self):
        p=project();p['nodes']=[node('a',order=0),node('b','100',order=1),node('c','200',order=2)]
        p['physical_model']={'constraints':[]};return p
    def coordinate(self,result,point,axis='X'):
        return next(p for p in result['coordinates'] if p['point_id']==point)['axes'][axis]

    def test_signed_coordinate_chains_and_evidence_are_exact(self):
        p=self.model();p['physical_model']['constraints']=[dimension('anchor','a',None,'1000',kind='COORDINATE'),dimension('ab','a','b','152.4'),dimension('bc','b','c','-53.975')]
        result=solve(p)
        self.assertEqual(self.coordinate(result,'c')['value_mm'],'1098.425')
        self.assertEqual(self.coordinate(result,'c','Y')['value_mm'],None)
        self.assertEqual(self.coordinate(result,'c','Y')['relative_mm'],None)
        self.assertFalse(result['issues'])
        group=self.coordinate(result,'c')['evidence_group']
        self.assertEqual(set(result['evidence_groups'][group]['constraint_ids']),{'anchor','ab','bc'})
        self.assertEqual(result['inputs'][2]['source_text'],'-53.975 mm')
        self.assertFalse(result['drawing_pixels_used']);self.assertFalse(result['physical_stations_modified'])

    def test_relative_only_deltas_do_not_invent_an_absolute_origin_or_zero_axes(self):
        p=self.model();p['physical_model']['constraints']=[dimension('ab','a','b','100')]
        result=solve(p)
        self.assertEqual(self.coordinate(result,'a')['status'],'RELATIVE_ONLY')
        self.assertEqual(self.coordinate(result,'b')['value_mm'],None)
        self.assertEqual(result['elements'][0]['delta_mm'],{'X':'100','Y':None,'Z':None})
        self.assertEqual(result['elements'][1]['delta_mm']['X'],None)
        self.assertEqual([n['station_mm'] for n in p['nodes']],['0','100','200'])

    def test_conflicting_cycles_and_anchors_return_no_false_coordinates(self):
        p=self.model();p['physical_model']['constraints']=[dimension('origin','a',None,'0',kind='COORDINATE'),dimension('ab','a','b','100'),dimension('bc','b','c','100'),dimension('wrong','a','c','201')]
        result=solve(p)
        self.assertTrue(result['issues'])
        self.assertTrue(all(self.coordinate(result,n)['status']=='CONFLICT' for n in ('a','b','c')))
        self.assertTrue(all(self.coordinate(result,n)['value_mm'] is None for n in ('a','b','c')))
        p['physical_model']['constraints'].pop();p['physical_model']['constraints'].append(dimension('wrong-origin','c',None,'201',kind='COORDINATE'))
        self.assertEqual(self.coordinate(solve(p),'c')['status'],'CONFLICT')

    def test_only_reviewed_sources_participate_and_declared_tolerances_are_retained(self):
        p=self.model();p['physical_model']['constraints']=[dimension('origin','a',None,'0',kind='COORDINATE'),dimension('ab','a','b','100'),dimension('bc','b','c','100'),dimension('near','a','c','200.005',tolerance='.01')]
        result=solve(p);self.assertFalse(result['issues'])
        self.assertEqual(next(c for c in result['inputs'] if c['id']=='near')['tolerance_mm'],'.01')
        p['physical_model']['constraints'][0]['verification']='proposed'
        result=solve(p);self.assertIsNone(self.coordinate(result,'a')['value_mm'])
        self.assertEqual(len(result['inputs']),3)

    def test_accepted_analysis_vectors_feed_the_same_constraints_without_station_scaling(self):
        p=self.model();p['analysis_model']={'elements':[{'id':'edge','from_point_id':'a','to_point_id':'b','dx_mm':'-53.975','dy_mm':'0','dz_mm':'100','evidence':'Engineer supplied signed XYZ','verification':'engineer-entered'}]}
        result=solve(p)
        self.assertEqual(result['elements'][0]['delta_mm'],{'X':'-53.975','Y':'0','Z':'100'})
        self.assertEqual(self.coordinate(result,'b')['value_mm'],None)
        p['nodes'][0]['instances']=[{'sheet_id':'sheet-a','anchor':[500,900],'bubble':[20,20]}]
        self.assertEqual(solve(p),result)
