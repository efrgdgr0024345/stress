"""Pure scalar rule records, never claimed as real 1010/golden engineering data."""
from copy import deepcopy
from decimal import Decimal
import unittest
from packages.engineering import dimension_mm,compute_reasons
from packages.physical.stations import (solve_stations,source_stamps,apply_station_reasons,
    manual_station_override,station_pair_comparable,MAX_POINTS,MAX_CONSTRAINTS)
from tests.unit.test_physical_model import project,node


def model(count=2):
    p=project();p['nodes']=[node(str(i),None,kind='support',order=i) for i in range(count)]
    p['physical_model']={'components':[],'constraints':[],'station_constraints':[]}
    return p


def add(p,kind,a,b,value,tolerance='0',identifier=None):
    c={'id':identifier or 'station-'+str(len(p['physical_model']['station_constraints'])),
       'kind':kind,'from_point_id':a,'to_point_id':b,'value_mm':str(value),'tolerance_mm':str(tolerance),
       'source_text':str(value)+' mm','source_format':'STANDARD','distance_basis':'ALONG_CENTRELINE',
       'sheet_id':'sheet-a','source_content_hash':deepcopy(p['sheets'][0]['content_hash']),
       'source_point_stamps':source_stamps(p,{a,b}-{None}),
       'evidence':'EXPLICIT PURE RULE FIXTURE: not a source fact or engineering approval for 1010.','verification':'reviewed'}
    p['physical_model']['station_constraints'].append(c)
    return c


def accept(p,solution):
    rows={r['point_id']:r for r in solution['points']}
    for n in p['nodes']:
        r=rows[n['id']]
        if not r['can_apply']:continue
        n['station_mm']=r['station_mm']
        n['station_proof']={k:deepcopy(r.get(k)) for k in ('basis','basis_id','basis_point_id','constraint_ids','input_sha256','retained_manual_anchor')}
        n['station_proof'].update(value_mm=r['station_mm'],line_id=n['line_id'],route=n['route'])
    apply_station_reasons(p)


class StationSolverTests(unittest.TestCase):
    def test_historic_support_lengths_remain_exact_scalar_distances_independent_of_paper_or_xyz(self):
        for text,expected,flag in [('2 in','50.8',True),('0.5 in','12.70',True),('2 1/8 in','53.975',True),('6 in','152.4',True),('152.4001 mm','152.4001',False)]:
            with self.subTest(text=text):
                p=model();p['nodes'][1]['instances'][0]['anchor']=[550,400]
                for i,n in enumerate(p['nodes']):n['coordinates_mm']={'X':str(i*10000),'Y':'0','Z':'0'}
                add(p,'DELTA','0','1',dimension_mm(text));add(p,'LOCAL_ORIGIN','0',None,'0')
                s=solve_stations(p);self.assertTrue(s['can_apply'])
                rows={r['point_id']:r for r in s['points']}
                self.assertEqual(Decimal(rows['1']['station_mm']),Decimal(expected))
                self.assertIsNone(rows['1']['absolute_station_mm'])
                self.assertEqual(rows['1']['basis'],'LOCAL_ORIGIN')
                self.assertTrue(all(n['station_mm'] is None for n in p['nodes']))
                accept(p,s);compute_reasons(p['nodes'])
                self.assertEqual('SUPPORT_WITHIN_6_IN' in p['nodes'][1]['reasons'],flag)
                self.assertFalse(s['drawing_pixels_used']);self.assertFalse(s['xyz_distance_used'])

    def test_delta_only_and_xyz_only_never_create_a_station_zero_or_absolute_datum(self):
        p=model();add(p,'DELTA','0','1','100')
        s=solve_stations(p)
        self.assertFalse(s['can_apply']);self.assertTrue(all(r['status']=='RELATIVE_ONLY' and r['station_mm'] is None for r in s['points']))
        p['physical_model']['station_constraints']=[]
        for i,n in enumerate(p['nodes']):n['coordinates_mm']={'X':str(i*100),'Y':'0','Z':'0'}
        self.assertTrue(all(r['station_mm'] is None for r in solve_stations(p)['points']))

    def test_recorded_evidence_stays_unknown_until_both_endpoints_have_the_same_explicit_route(self):
        p=model();add(p,'DELTA','0','1','100');add(p,'LOCAL_ORIGIN','0',None,'0')
        for n in p['nodes']:n.update(route=None,order=None,topology_state='UNASSIGNED')
        s=solve_stations(p);self.assertFalse(s['can_apply']);self.assertTrue(all(r['status']=='TOPOLOGY_REQUIRED' for r in s['points']))
        for i,n in enumerate(p['nodes']):n.update(route='main',order=i,topology_state='ASSIGNED')
        self.assertTrue(solve_stations(p)['can_apply'])
        p['nodes'][1]['route']='branch-01'
        self.assertFalse(solve_stations(p)['can_apply'])
        self.assertTrue(any(i['code']=='STATION_ROUTE_REQUIRED' for i in solve_stations(p)['issues']))

    def test_conflicting_chains_never_average_or_overwrite_manual_stations(self):
        p=model(3);p['nodes'][0]['station_mm']='1000'
        add(p,'DELTA','0','1','100');add(p,'DELTA','1','2','100');add(p,'DELTA','0','2','250')
        before=deepcopy(p);s=solve_stations(p)
        self.assertEqual(p,before);self.assertFalse(s['can_apply'])
        self.assertTrue(all(r['status']=='CONFLICT' and r['station_mm'] is None for r in s['points']))
        self.assertTrue(any(i['code']=='STATION_CONSTRAINT_CONFLICT' for i in s['issues']))

    def test_source_tolerances_never_generate_an_averaged_offset(self):
        p=model();add(p,'DELTA','0','1','0');add(p,'ABSOLUTE','0',None,'100','2');add(p,'ABSOLUTE','1',None,'104','2')
        s=solve_stations(p);self.assertFalse(s['can_apply'])
        self.assertTrue(all(r['status']=='TOLERANCE_REVIEW' and r['station_mm'] is None for r in s['points']))
        self.assertTrue(any(i['code']=='STATION_TOLERANCE_REVIEW' for i in s['issues']))
        p=model();add(p,'DELTA','0','1','0');add(p,'ABSOLUTE','0',None,'100','5');add(p,'ABSOLUTE','1',None,'101','0')
        self.assertEqual({r['station_mm'] for r in solve_stations(p)['points']},{'101'})

    def test_absolute_and_declared_relative_datums_are_kept_distinct(self):
        p=model();add(p,'DELTA','0','1','50.8');add(p,'LOCAL_ORIGIN','0',None,'0');add(p,'ABSOLUTE','0',None,'1000')
        s=solve_stations(p);rows={r['point_id']:r for r in s['points']}
        self.assertEqual(rows['1']['absolute_station_mm'],'1050.8');self.assertEqual(rows['1']['relative_station_mm'],'50.8')
        self.assertEqual(rows['1']['basis'],'ABSOLUTE')
        p['physical_model']['station_constraints']=[c for c in p['physical_model']['station_constraints'] if c['kind']!='ABSOLUTE']
        add(p,'LOCAL_ORIGIN','1',None,'0')
        s=solve_stations(p);self.assertFalse(s['can_apply'])
        self.assertTrue(any(i['code']=='STATION_MULTIPLE_LOCAL_ORIGINS' for i in s['issues']))

    def test_two_disconnected_local_datums_on_one_route_do_not_create_a_support_gap(self):
        p=model();add(p,'LOCAL_ORIGIN','0',None,'0');add(p,'LOCAL_ORIGIN','1',None,'0')
        accept(p,solve_stations(p));compute_reasons(p['nodes'])
        self.assertFalse(station_pair_comparable(*p['nodes']))
        self.assertTrue(all(n.get('support_gap_mm') is None for n in p['nodes']))
        self.assertTrue(all('SUPPORT_WITHIN_6_IN' not in n['reasons'] for n in p['nodes']))

    def test_a_new_competing_origin_stales_existing_proof_and_suppresses_old_support_gaps(self):
        p=model();add(p,'DELTA','0','1','100');add(p,'LOCAL_ORIGIN','0',None,'0')
        accept(p,solve_stations(p));before=[n['station_mm'] for n in p['nodes']]
        add(p,'LOCAL_ORIGIN','1',None,'0');apply_station_reasons(p);compute_reasons(p['nodes'])
        self.assertEqual([n['station_mm'] for n in p['nodes']],before)
        self.assertTrue(all('STATION_MULTIPLE_LOCAL_ORIGINS' in n['station_review_reasons'] for n in p['nodes']))
        self.assertTrue(all('STATION_SOLUTION_STALE' in n['station_review_reasons'] for n in p['nodes']))
        self.assertFalse(station_pair_comparable(*p['nodes']))
        self.assertTrue(all(n['support_gap_mm'] is None for n in p['nodes']))

    def test_decimal_negation_never_rounds_a_long_exact_source_length_to_the_global_context(self):
        p=model();value='0.123456789012345678901234567890123456789'
        add(p,'DELTA','0','1',value);add(p,'LOCAL_ORIGIN','0',None,'0')
        s=solve_stations(p)
        self.assertTrue(s['can_apply'])
        self.assertEqual(s['points'][1]['station_mm'],value)
        self.assertFalse(any(i['code']=='STATION_CONSTRAINT_CONFLICT' for i in s['issues']))

    def test_applied_proof_does_not_feed_back_but_changes_stale_it_without_moving_values(self):
        p=model();d=add(p,'DELTA','0','1','53.975');add(p,'LOCAL_ORIGIN','0',None,'0')
        s=solve_stations(p);accept(p,s)
        self.assertFalse(any(i['code']=='STATION_SOLUTION_STALE' for i in solve_stations(p)['issues']))
        p['nodes'][1]['instances'][0]['bubble']=[450,300]
        self.assertFalse(any(i['code']=='STATION_SOLUTION_STALE' for i in solve_stations(p)['issues']))
        d['value_mm']='50.8';d['source_text']='50.8 mm'
        s=solve_stations(p);self.assertEqual(p['nodes'][1]['station_mm'],'53.975')
        self.assertTrue(any(i['code']=='STATION_SOLUTION_STALE' for i in s['issues']))
        self.assertEqual(next(r for r in s['points'] if r['point_id']=='1')['station_mm'],'50.8')
        p['nodes'][1]['instances'][0]['anchor']=[100,100]
        self.assertFalse(solve_stations(p)['can_apply'])
        self.assertTrue(any(i['code']=='STATION_SOURCE_STALE' for i in solve_stations(p)['issues']))

    def test_manual_override_archives_proof_keeps_its_datum_and_reports_real_source_conflicts(self):
        p=model();d=add(p,'DELTA','0','1','100');add(p,'LOCAL_ORIGIN','0',None,'0')
        accept(p,solve_stations(p));n=p['nodes'][1];old=deepcopy(n['station_proof'])
        self.assertTrue(manual_station_override(n,'150'));n['station_mm']='150'
        self.assertEqual(n['station_proof_history'],[old]);self.assertNotIn('station_proof',n)
        self.assertEqual(n['manual_station_basis']['basis_id'],old['basis_id'])
        s=solve_stations(p)
        self.assertTrue(any(i['code']=='STATION_CONSTRAINT_CONFLICT' for i in s['issues']))
        self.assertFalse(any(i['code']=='STATION_SOLUTION_STALE' and n['id'] in i['point_ids'] for i in s['issues']))
        d['value_mm']='150';d['source_text']='150 mm'
        self.assertTrue(solve_stations(p)['can_apply'])
        manual_station_override(n,None);n['station_mm']=None
        self.assertNotIn('manual_station_basis',n)

    def test_manual_anchors_are_retained_after_explicit_apply_without_self_staleness(self):
        p=model();p['nodes'][0]['station_mm']='1000';add(p,'DELTA','0','1','100')
        s=solve_stations(p);self.assertEqual(s['points'][1]['station_mm'],'1100')
        accept(p,s)
        self.assertTrue(p['nodes'][0]['station_proof']['retained_manual_anchor'])
        self.assertFalse(any(i['code']=='STATION_SOLUTION_STALE' for i in solve_stations(p)['issues']))

    def test_new_unrelated_constraints_do_not_stale_an_accepted_station_component(self):
        p=model(3);add(p,'DELTA','0','1','100');add(p,'LOCAL_ORIGIN','0',None,'0')
        accept(p,solve_stations(p));add(p,'ABSOLUTE','2',None,'3000')
        self.assertFalse(any(i['code']=='STATION_SOLUTION_STALE' for i in solve_stations(p)['issues']))

    def test_bounds_fail_explicitly_instead_of_emitting_partial_stations(self):
        p=model();p['nodes']=[dict(node(str(i),None),order=i) for i in range(MAX_POINTS+1)]
        s=solve_stations(p);self.assertFalse(s['can_apply']);self.assertEqual(s['points'],[])
        self.assertEqual(s['issues'][0]['code'],'STATION_SOLVER_LIMIT')
