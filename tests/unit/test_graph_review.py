"""Graph rule inputs are labelled software vectors; real-source geometry stays unknown."""
from copy import deepcopy
import random
import unittest

from packages.engineering import renumber,topology,record_source_location_review
from packages.engineering.graph_review import (audit_graph,preview_topology,apply_topology,
    renumber_project,record_point_topology_review)
from tests.unit.test_engineering import point
from tests.unit.test_physical_model import project,dimension
from tests.unit import test_source_exceptions as source_fixture

REASON='SOFTWARE VALIDATION ONLY: explicit inspected topology vector, not real 1010 engineering acceptance.'
REVIEWER='SOFTWARE-ONLY-TOPOLOGY-REVIEWER'
WHEN='2026-11-25T00:00:00+00:00'


def rule_project(nodes):
    p=project();p.update(id='SOFTWARE-ONLY-GRAPH-VECTOR',version=1,line_id='A',nodes=nodes)
    p['sheets'][0]['line_id']='A'
    return p


def assignment(node,state='ASSIGNED',route='main',order=0,takeoff=None):
    return {'point_id':node['id'],'topology_state':state,'line_id':node['line_id'],
        'route':route if state=='ASSIGNED' else None,'order':order if state=='ASSIGNED' else None,
        'takeoff_id':takeoff,'topology_confirmed':state=='ASSIGNED'}


class GraphReviewTests(unittest.TestCase):
    def real_source(self):
        return source_fixture.SourceExceptionTests().model()

    def inspect(self,p,node):
        for observation in [node['source_observation']]:
            sheet=next(s for s in p['sheets'] if s['id']==observation['sheet_id'])
            instance=next(i for i in node['instances'] if i['sheet_id']==sheet['id'])
            record_source_location_review(node,{'sheet_id':sheet['id'],'source_sha256':sheet['sha256'],
                'content_hash':sheet['content_hash'],'anchor':deepcopy(instance['anchor']),
                'evidence':REASON,'reviewed_by':REVIEWER,'reviewed_at':WHEN})

    def test_line_and_branch_numbering_are_independent_of_input_array_order(self):
        nodes=[point(0,line='A',kind='tee'),point(1,line='A',kind='tee'),point(2,line='A')]
        nodes += [point(20+i,line='A',route='branch-01') for i in range(16)]
        nodes += [point(50,line='A',route='branch-02'),point(90,line='B'),point(91,line='B')]
        for node in nodes:
            if node['route']=='branch-01':node['takeoff_id']='1'
            if node['route']=='branch-02':node['takeoff_id']='0'
        original=deepcopy(nodes);expected=None
        for seed in range(6):
            trial=deepcopy(original);random.Random(seed).shuffle(trial)
            renumber(trial,primary_line='B');labels={n['id']:n['number'] for n in trial}
            if expected is None:expected=labels
            self.assertEqual(labels,expected)
            for node in trial:
                before=next(n for n in original if n['id']==node['id'])
                self.assertEqual({k:v for k,v in node.items() if k!='number'},
                                 {k:v for k,v in before.items() if k!='number'})
        self.assertEqual(expected['90'],10);self.assertEqual(expected['91'],20)
        self.assertEqual(expected['0'],1000);self.assertEqual(expected['50'],1100)
        self.assertEqual(expected['20'],1200);self.assertEqual(expected['35'],1350)

    def test_numbering_failure_on_a_later_line_is_atomic_and_duplicate_order_never_guesses_edges(self):
        nodes=[point(1,line='A'),point(2,line='B',route='branch-01')]
        nodes[0]['number']=900;before=deepcopy(nodes)
        with self.assertRaisesRegex(ValueError,'main route'):renumber(nodes)
        self.assertEqual(nodes,before)
        nodes=[point(1),point(2)];nodes[1]['order']=nodes[0]['order'];before=deepcopy(nodes)
        with self.assertRaisesRegex(ValueError,'duplicate route order'):renumber(nodes)
        self.assertEqual(nodes,before);self.assertEqual(topology(nodes)['edges'],[])
        self.assertIn('DUPLICATE_ROUTE_ORDER',{i['code'] for i in audit_graph(rule_project(nodes))['issues']})

    def test_branch_attachment_requires_one_common_assigned_same_line_main_tee(self):
        for invalid in ('missing','not-tee','foreign-line','unassigned','mixed'):
            with self.subTest(invalid=invalid):
                tee=point(0,kind='tee');end=point(1);a=point(2,route='branch-01');b=point(3,route='branch-01')
                a['takeoff_id']=b['takeoff_id']='0'
                if invalid=='missing':a['takeoff_id']=b['takeoff_id']=None
                if invalid=='not-tee':tee['kind']='endpoint'
                if invalid=='foreign-line':tee['line_id']='B'
                if invalid=='unassigned':tee.update(topology_state='UNASSIGNED',route=None,order=None)
                if invalid=='mixed':b['takeoff_id']=None
                nodes=[tee,end,a,b];g=topology(nodes)
                self.assertFalse(any(e['from']=='0' and e['to']=='2' for e in g['edges']))
                report=audit_graph(rule_project(nodes));codes={i['code'] for i in report['structural_issues']}
                self.assertTrue(codes&{'BRANCH_TAKEOFF_REQUIRED','BRANCH_TAKEOFF_INVALID','BRANCH_TAKEOFF_INCONSISTENT'})
                self.assertFalse(report['can_apply'])

    def test_real_47_source_points_remain_visible_unassigned_with_no_guessed_number_or_edge(self):
        p=self.real_source();before=deepcopy(p);report=preview_topology(p,[],REASON)
        self.assertEqual(p,before);self.assertEqual(report['summary']['points'],47)
        self.assertEqual(report['summary']['unassigned'],47);self.assertEqual(report['graph']['edges'],[])
        self.assertEqual({r['point_id'] for r in report['numbering_map']},{n['id'] for n in p['nodes']})
        self.assertTrue(all(r['new'] is None for r in report['numbering_map']))
        self.assertEqual(len([i for i in report['issues'] if i['code']=='TOPOLOGY_UNASSIGNED']),47)
        self.assertEqual(len([i for i in report['issues'] if i['code']=='GRAPH_STATION_UNPROVED']),47)
        self.assertFalse(report['summary']['complete'])

    def test_real_source_batch_requires_separate_inspection_and_preserves_unknown_geometry(self):
        p=self.real_source();node=p['nodes'][0];rows=[assignment(node)]
        with self.assertRaisesRegex(ValueError,'Independently inspect'):preview_topology(p,rows,REASON)
        self.inspect(p,node);before=deepcopy(p['nodes']);preview=preview_topology(p,rows,REASON)
        self.assertTrue(preview['can_apply']);self.assertEqual(p['nodes'],before)
        apply_topology(p,rows,REASON,preview['preview_sha256'],REVIEWER,WHEN)
        selected=next(n for n in p['nodes'] if n['id']==node['id'])
        self.assertEqual(selected['number'],10);self.assertEqual(selected['id'],node['id'])
        self.assertEqual(selected['instances'],node['instances']);self.assertIsNone(selected['station_mm'])
        self.assertNotIn('coordinates_mm',selected);self.assertEqual(selected['source_review_reasons'],node['source_review_reasons'])
        self.assertEqual(selected['topology_proof']['reviewed_by'],REVIEWER)
        self.assertTrue(all(n['route'] is None and n['order'] is None and n['number'] is None
                            for n in p['nodes'] if n['id']!=selected['id']))

    def test_preview_is_bound_to_exact_evidence_and_current_source_context(self):
        p=self.real_source();node=p['nodes'][0];self.inspect(p,node);rows=[assignment(node)]
        preview=preview_topology(p,rows,REASON);before=deepcopy(p)
        with self.assertRaisesRegex(ValueError,'preview'):apply_topology(p,rows,REASON+' Changed',preview['preview_sha256'],REVIEWER,WHEN)
        self.assertEqual(p,before)
        node['instances'][0]['anchor'][0]+=1;before=deepcopy(p)
        with self.assertRaisesRegex(ValueError,'Independently inspect'):apply_topology(p,rows,REASON,preview['preview_sha256'],REVIEWER,WHEN)
        self.assertEqual(p,before)

    def test_bubble_number_changes_preserve_topology_proof_but_anchor_changes_invalidate_it(self):
        p=self.real_source();node=p['nodes'][0];self.inspect(p,node)
        node.update(route='main',order=0,topology_state='ASSIGNED')
        record_point_topology_review(p,[node['id']],REASON,REVIEWER,WHEN)
        proof=deepcopy(node['topology_proof']);node['instances'][0]['bubble'][0]+=10;node['number']=345
        self.assertNotIn('TOPOLOGY_REVIEW_STALE',{i['code'] for i in audit_graph(p)['structural_issues']})
        self.assertEqual(node['topology_proof'],proof)
        node['instances'][0]['anchor'][0]+=1
        codes={i['code'] for i in audit_graph(p)['structural_issues']}
        self.assertTrue({'TOPOLOGY_REVIEW_STALE','SOURCE_LOCATION_REVIEW_REQUIRED'}<=codes)

    def test_meaningful_map_and_all_instances_survive_repeat_numbering(self):
        a=point(0,station='0',kind='continuation');b=point(1,station='50.8')
        a['instances'].append({'sheet_id':'sheet-b','anchor':[15,20],'bubble':[30,40]})
        a['reasons']=['UNVERIFIED_DIMENSION'];a['station_proof']={'software_only':'retained'}
        p=rule_project([a,b]);original=deepcopy(p['nodes'])
        renumber_project(p,'Software-only first numbering',REVIEWER,WHEN)
        history=deepcopy(p['numbering_history']);mapping=deepcopy(p['numbering_map'])
        self.assertEqual(len(history),1);self.assertEqual(len(history[0]['point_instances']['0']),2)
        renumber_project(p,'Software-only repeat numbering',REVIEWER,WHEN)
        self.assertEqual(p['numbering_history'],history);self.assertEqual(p['numbering_map'],mapping)
        for node,before in zip(p['nodes'],original):
            self.assertEqual({k:v for k,v in node.items() if k!='number'},{k:v for k,v in before.items() if k!='number'})

    def test_source_register_identity_and_feature_provenance_are_bound_to_the_route_proof(self):
        p=self.real_source();node=p['nodes'][0];self.inspect(p,node)
        node.update(route='main',order=0,topology_state='ASSIGNED')
        record_point_topology_review(p,[node['id']],REASON,REVIEWER,WHEN)
        original=deepcopy(p)
        sheet=next(s for s in p['sheets'] if s['id']==node['instances'][0]['sheet_id'])
        sheet['line_id']='SOFTWARE-ONLY-CHANGED-REGISTER'
        codes={i['code'] for i in audit_graph(p)['structural_issues']}
        self.assertTrue({'POINT_SOURCE_LINE_MISMATCH','TOPOLOGY_REVIEW_STALE'}<=codes)
        p=deepcopy(original);p['nodes'][0]['source_feature_id']='SOFTWARE-ONLY-CHANGED-PROVENANCE'
        self.assertIn('TOPOLOGY_REVIEW_STALE',{i['code'] for i in audit_graph(p)['structural_issues']})

    def test_qualified_relative_xyz_requires_an_explicit_current_local_model_origin(self):
        p=rule_project([point(0,station='0'),point(1,station='100')])
        p['physical_model']={'components':[],'constraints':[dimension('software-only-'+axis,'0','1','100' if axis=='X' else '0',axis=axis) for axis in ('X','Y','Z')]}
        self.assertIn('GRAPH_XYZ_UNPROVED',{i['code'] for i in audit_graph(p)['geometry_issues']})
        p['analysis_model']={'local_origin_confirmed':True,'origin_point_id':'0'}
        self.assertNotIn('GRAPH_XYZ_UNPROVED',{i['code'] for i in audit_graph(p)['geometry_issues']})
        self.assertTrue(all(n.get('coordinates_mm') is None for n in p['nodes']))

    def test_duplicate_alias_rows_and_nonintegral_import_orders_do_not_become_connections(self):
        p=rule_project([point(0)]);p['point_aliases']={'old':'0'}
        rows=[assignment(p['nodes'][0]),{**assignment(p['nodes'][0]),'point_id':'old'}]
        with self.assertRaisesRegex(ValueError,'repeat'):preview_topology(p,rows,REASON)
        for order in (-1,True,None):
            p=rule_project([point(0),point(1)]);p['nodes'][0]['order']=order
            self.assertEqual(topology(p['nodes'])['edges'],[])
            self.assertIn('TOPOLOGY_ASSIGNMENT_INVALID',{i['code'] for i in audit_graph(p)['structural_issues']})

    def test_shared_depictions_need_independent_inspections_and_topology_does_not_accept_a_proposed_station(self):
        # Pure review-state vector only: these are not asserted real 1010
        # depictions or source dimensions.
        n=point(0,station='100');n.update(verification='proposed',topology_state='UNASSIGNED',route=None,order=None)
        n['instances'].append({'sheet_id':'sheet-b','anchor':[15,25],'bubble':[35,45]})
        first={'id':'SOFTWARE-ONLY-A','sheet_id':'sheet-a','content_hash':['a'*64],'verification':'proposed'}
        second={'id':'SOFTWARE-ONLY-B','sheet_id':'sheet-b','content_hash':['b'*64],'verification':'proposed'}
        n['source_observation']=first;n['source_observations']=[first,second]
        p=rule_project([n]);p['sheets'].append({**p['sheets'][0],'id':'sheet-b','content_hash':['b'*64]})
        for index,sheet in enumerate(p['sheets']):
            instance=next(i for i in n['instances'] if i['sheet_id']==sheet['id'])
            record_source_location_review(n,{'sheet_id':sheet['id'],'content_hash':sheet['content_hash'],
                'anchor':deepcopy(instance['anchor']),'reviewed_by':REVIEWER,'reviewed_at':WHEN,'evidence':REASON})
            if index==0:
                with self.assertRaisesRegex(ValueError,'every current source depiction'):
                    preview_topology(p,[assignment(n)],REASON)
        preview=preview_topology(p,[assignment(n)],REASON)
        self.assertTrue(preview['can_apply']);apply_topology(p,[assignment(n)],REASON,preview['preview_sha256'],REVIEWER,WHEN)
        self.assertEqual(p['nodes'][0]['station_mm'],'100')
        self.assertEqual(p['nodes'][0]['verification'],'proposed')
        self.assertNotIn('station_proof',p['nodes'][0])
        self.assertIn('GRAPH_STATION_UNPROVED',{i['code'] for i in audit_graph(p)['geometry_issues']})
