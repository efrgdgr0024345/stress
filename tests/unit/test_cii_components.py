"""Explicit SOFTWARE-ONLY vectors; no values qualify the real 1010 model."""
from copy import deepcopy
from decimal import Decimal
import unittest

from packages.automation.recognize import identity
from packages.physical.stations import source_stamps,basis_id
from packages.workbooks.caesar_neutral import assess,neutral_file
from packages.workbooks.cii_components import native_component_plan,save_record
from tests.unit.test_neutral_export import model as straight_model,sections,numbers
from tests.unit import test_source_exceptions as source_fixture

EVIDENCE='SOFTWARE VALIDATION ONLY: explicit neutral-contract input, not actual 1010 engineering acceptance.'
REVIEWER='SOFTWARE-ONLY-CII-REVIEWER'
WHEN='2026-11-25T00:00:00+00:00'


def software_model(with_records=True):
    """Four invented rule-vector points, expressly unrelated to real drawings."""
    p=straight_model();p.update(id='SOFTWARE-ONLY-CII-COMPONENT-VECTOR',
        title='SOFTWARE VALIDATION ONLY - NO REAL ENGINEERING INPUT')
    base=deepcopy(p['analysis_model']['elements'][0]);p['nodes']=[];p['analysis_model']['elements']=[]
    p['sheets']=[{'id':'SOFTWARE-ONLY-SHEET','source_id':'SOFTWARE-ONLY-SOURCE','page_index':0,
        'sha256':'a'*64,'content_hash':['b'*64],'line_id':p['line_id'],'printed_id':'SOFTWARE-ONLY-SHEET',
        'identity_verified':True,'width':600,'height':500,'rotation':0,'filename':'SOFTWARE-ONLY.pdf','format':'Software vector'}]
    rows=[('a',10,'main',0,'0','endpoint'),('t',20,'main',1,'1000','tee'),
          ('c',30,'main',2,'2000','valve'),('b',100,'branch-01',0,'500','support')]
    for index,(uid,number,route,order,station,kind) in enumerate(rows):
        node={'id':uid,'number':number,'line_id':p['line_id'],'route':route,'order':order,'kind':kind,
            'station_mm':station,'evidence':EVIDENCE,'verification':'reviewed','instances':[
                {'sheet_id':'SOFTWARE-ONLY-SHEET','anchor':[50+100*index,100],'bubble':[80+100*index,80]}]}
        if route!='main':node['takeoff_id']='t'
        p['nodes'].append(node)
    for a,b,delta in [('a','t',('1000','0','0')),('t','c',('1000','0','0')),('t','b',('0','500','0'))]:
        element=deepcopy(base);element.update(id=identity(p['id'],a,b),from_point_id=a,to_point_id=b,
            dx_mm=delta[0],dy_mm=delta[1],dz_mm=delta[2],evidence=EVIDENCE,verification='engineer-entered')
        p['analysis_model']['elements'].append(element)
    p['analysis_model'].update(origin_point_id='a',piping_code_id=53)
    return add_reviewed_records(p) if with_records else p


def record_inputs(project):
    """Canonical units and deliberate choices; no defaults represent unknowns."""
    return [
        {'kind':'RIGID','point_id':'c','element_id':identity(project['id'],'t','c'),
         'values':{'weight_n':'444.82216152605','rigid_type':'1','weight_scope':'COMPONENT_TOTAL_EXCLUDES_FLUID_INSULATION'}},
        {'kind':'TEE','point_id':'t','element_id':identity(project['id'],'a','t'),
         'values':{'tee_type':'3','in_plane_sif':'1.25','out_plane_sif':'1.5','axial_sif':'1.1',
            'torsion_sif':'1.2','pressure_sif':'1.3','in_plane_index':'1.4','out_plane_index':'1.6',
            'axial_index':'1.7','torsion_index':'1.8','pressure_index':'1.9',
            'code_note_1':'UNSPECIFIED','code_note_2':'CLEARED','no_geometry_overrides':True}},
        {'kind':'RESTRAINT','point_id':'b','element_id':identity(project['id'],'t','b'),
         'values':{'type_code':'14','axis_basis':'TARGET_CAESAR_AXES','grounded':True,
            'stiffness_n_per_mm':'1000','gap_mm':'25.4','friction_coefficient':'.2',
            'support_tag':'SOFTWARE SUPPORT','support_guid':'SOFTWARE-GUID'}}]


def add_reviewed_records(project):
    """Rebuild fresh source-context receipts after a deliberate fixture change."""
    project['analysis_model']['native_components']=[]
    for data in record_inputs(project):
        save_record(project,{**deepcopy(data),'component_id':None,'source_sheet_id':'SOFTWARE-ONLY-SHEET',
            'review_state':'REVIEWED','evidence':EVIDENCE},REVIEWER,WHEN)
    return project


class CiiComponentTests(unittest.TestCase):
    def test_complete_explicit_software_vector_serializes_documented_counts_pointers_and_units(self):
        p=software_model();self.assertEqual(native_component_plan(p)['issues'],[])
        check=assess(p);self.assertTrue(check['available'],check);self.assertFalse(check['qualified_application_roundtrip'])
        result=sections(neutral_file(p));control=numbers(result['CONTROL'][1:])
        self.assertEqual(control[1],1);self.assertEqual(control[3],1);self.assertEqual(control[10],1)
        self.assertEqual(len(result['RIGID']),1);self.assertEqual(numbers(result['RIGID']),[100,1])
        self.assertEqual(len(result['RESTRANT']),24);self.assertEqual(len(result['SIF&TEES']),14)
        expected=[(0,0,1),(1,0,0),(0,1,0)]
        for index,(rigid,restraint,tee) in enumerate(expected):
            pointer=numbers(result['ELEMENTS'][15*index+12:15*index+15])
            self.assertEqual(len(pointer),15);self.assertEqual((pointer[1],pointer[3],pointer[10]),(rigid,restraint,tee))
        restraint=numbers(result['RESTRANT'][:2]);self.assertEqual(restraint[:2],[100,14])
        self.assertAlmostEqual(float(restraint[2]),float(Decimal('1000')*Decimal('25.4')/Decimal('4.4482216152605')),places=3)
        self.assertEqual(restraint[3:],[1,Decimal('.2'),0,0,0,0])
        tee=numbers(result['SIF&TEES']);self.assertEqual(len(tee),84)
        self.assertEqual(tee[:4],[20,3,Decimal('1.25'),Decimal('1.5')])
        self.assertEqual(tee[22:24],[Decimal('9999.99'),0])
        self.assertEqual(result['BEND'],[])

    def test_real_1010_draft_bend_retains_cod_unknown_and_specific_external_contract_gates(self):
        p=source_fixture.SourceExceptionTests().model();p['title']='SOFTWARE ONLY actual source BEND gate'
        component=next(c for c in p['physical_model']['components'] if c['kind']=='elbow')
        before=deepcopy(p['nodes']);save_record(p,{'kind':'BEND','component_id':component['id'],
            'point_id':None,'element_id':None,'source_sheet_id':component['sheet_id'],'review_state':'DRAFT',
            'values':{},'evidence':EVIDENCE},REVIEWER,WHEN)
        plan=native_component_plan(p);codes={i['code'] for i in plan['issues']}
        self.assertTrue({'BEND_NATIVE_GEOMETRY_CONTRACT_UNVERIFIED','BEND_NEUTRAL_FIELD_LAYOUT_AMBIGUOUS','NATIVE_COMPONENT_DRAFT'}<=codes)
        self.assertEqual(plan['bends'],[]);self.assertEqual(p['nodes'],before)
        self.assertTrue(all(n['station_mm'] is None and n['number'] is None for n in p['nodes']))
        self.assertFalse(assess(p)['available'])
        with self.assertRaisesRegex(ValueError,'BEND'):neutral_file(p)

    def test_draft_null_zero_weight_and_special_restraint_values_cannot_be_serialized(self):
        variants=[('RIGID',{},'DRAFT'),('RIGID',{'weight_n':'0'},'REVIEWED'),
                  ('RESTRAINT',{'type_code':'27'},'REVIEWED'),('RESTRAINT',{'gap_mm':None},'REVIEWED')]
        for kind,changes,state in variants:
            with self.subTest(kind=kind,changes=changes,state=state):
                p=software_model();record=next(r for r in p['analysis_model']['native_components'] if r['kind']==kind)
                data={k:deepcopy(record.get(k)) for k in ('kind','point_id','element_id','component_id','source_sheet_id','values','evidence')}
                data.update(review_state=state)
                data['values']={} if not changes else {**data['values'],**changes}
                save_record(p,data,REVIEWER,WHEN,record['id'])
                self.assertFalse(assess(p)['available'])
                self.assertTrue(native_component_plan(p)['issues'])
                with self.assertRaises(ValueError):neutral_file(p)

    def test_source_vectors_and_native_settings_stale_source_bound_records(self):
        for change in ('source','vector','settings','evidence','review_state'):
            with self.subTest(change=change):
                p=software_model()
                if change=='source':p['sheets'][0]['sha256']='c'*64
                elif change=='vector':p['analysis_model']['elements'][1]['dx_mm']='1001'
                elif change=='settings':p['analysis_model']['vertical_axis']='Y'
                elif change=='evidence':p['analysis_model']['native_components'][0]['evidence']+=' changed'
                else:p['analysis_model']['native_components'][0]['review_state']='DRAFT'
                self.assertIn('NATIVE_COMPONENT_REVIEW_STALE',{i['code'] for i in native_component_plan(p)['issues']})
                self.assertFalse(assess(p)['available'])

    def test_numbering_and_bubble_edits_preserve_identity_bound_component_inputs(self):
        p=software_model();before=deepcopy(p['analysis_model']['native_components'])
        p['nodes'][1]['number']=22000;p['nodes'][0]['instances'][0]['bubble'][0]+=12
        plan=native_component_plan(p);self.assertTrue(all(r['current'] for r in plan['records']))
        self.assertEqual(p['analysis_model']['native_components'],before)
        self.assertTrue(assess(p)['available'],assess(p))
        self.assertEqual(numbers(sections(neutral_file(p))['SIF&TEES'])[0],22000)

    def test_native_branch_geometry_never_subtracts_station_values_from_distinct_route_datums(self):
        p=software_model(with_records=False);branch=next(n for n in p['nodes'] if n['id']=='b');branch['station_mm']='0'
        branch['manual_station_basis']={'basis':'LOCAL_ORIGIN','basis_id':basis_id('LOCAL_ORIGIN',p['line_id'],'branch-01','b'),
            'basis_point_id':'b','line_id':p['line_id'],'route':'branch-01'}
        p['physical_model']={'components':[],'constraints':[],'station_constraints':[{
            'id':'SOFTWARE-ONLY-BRANCH-DATUM','kind':'LOCAL_ORIGIN','from_point_id':'b','to_point_id':None,
            'value_mm':'0','tolerance_mm':'0','source_text':'0 mm','distance_basis':'ALONG_CENTRELINE',
            'sheet_id':'SOFTWARE-ONLY-SHEET','source_sha256':p['sheets'][0]['sha256'],
            'source_content_hash':p['sheets'][0]['content_hash'],'source_point_stamps':source_stamps(p,{'b'}),
            'evidence':EVIDENCE,'verification':'reviewed'}]}
        add_reviewed_records(p)
        self.assertTrue(assess(p)['available'],assess(p));self.assertTrue(neutral_file(p))
