"""Real-source endpoint dispositions; generic merge records are not 1010 proof."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from packages.engineering import topology,renumber,source_observations
from packages.engineering.continuations import (assess_pair,merge_identity,source_review_states,
    source_review_records,create_source_exception,source_stamp,identity_audit)
from tests.integration import test_api as fixtures
from tests.unit.test_continuations import fixture
from tests.integration import test_continuations as existing_continuations
from services.api import main

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'


class SourceDecisionApiTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    upload=fixtures.ApiTests.upload

    def create(self):
        r=self.client.post('/api/v1/projects',json={'title':'Real 1010 source-decision software contract',
            'line_id':'8-PG-JE3LN2-1010-FUTURE'})
        self.assertEqual(r.status_code,201,r.text)
        return r.json()

    def model(self):
        p=self.upload(self.create(),SOURCE.read_bytes())
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/source-points",json={'version':p['version'],'confirmed':True})
        self.assertEqual(r.status_code,200,r.text)
        p=r.json();self.assertEqual(len(p['automation']['continuation_candidates']),4)
        return p

    def candidate(self,p):
        return next(c for c in p['automation']['continuation_candidates'] if c['target_kind']=='EXTERNAL_PIPING_LINE')

    def decide(self,p,candidate,decision='REJECT_MATCH',**changes):
        body={'version':p['version'],'decision':decision,'reason_code':'MISSING_PEER_IN_PACK',
              'evidence':'SOFTWARE TEST: actual source names an external peer not included in this drawing pack; no physical connection or XYZ is accepted.',
              'confirmed':True}
        body.update(changes)
        return self.client.post(f"/api/v1/projects/{p['id']}/continuations/sources/{candidate['id']}/decision",json=body)

    def report(self,p):
        return self.client.get(f"/api/v1/projects/{p['id']}/continuations").json()

    def test_machine_exceptions_are_explicit_proposals_not_engineer_approvals(self):
        p=self.model();report=self.report(p)
        self.assertEqual(len(report['source_reviews']),4)
        self.assertTrue(all(r['current'] and r['is_latest'] and not r['stale'] for r in report['source_reviews']))
        self.assertTrue(all(r['verification']=='proposed' and not r['engineering_approved'] and 'reviewed_by' not in r for r in report['source_reviews']))
        self.assertTrue(all(s['status']=='ENDPOINT_EXCEPTION' for s in report['source_review_states'].values()))
        self.assertEqual(sum(i['code']=='CONTINUATION_ENDPOINT_EXCEPTION' for i in report['issues']),4)
        self.assertFalse(any(i['code']=='UNRESOLVED_CONTINUATION_REFERENCE' for i in report['issues']))
        original=deepcopy(p)
        c=self.candidate(p)
        create_source_exception(p,c,'SOURCE_INTERFACE_UNCONFIRMED','A later machine observation must not replace a current record.')
        self.assertEqual(p,original)
        self.assertEqual(topology(p['nodes'])['edges'],[])
        self.assertTrue(all(n['station_mm'] is None and n['number'] is None for n in p['nodes']))

    def test_boundary_reopen_reject_history_preserves_every_unknown_point_and_source(self):
        p=self.model();c=self.candidate(p);before=deepcopy(p['nodes'])
        def physical(nodes):
            return [{k:v for k,v in node.items() if k not in ('reasons','continuation_review_reasons')} for node in nodes]
        for decision,status in [('DECLARE_EXTERNAL_BOUNDARY','EXTERNAL_BOUNDARY'),('REOPEN','REOPENED'),('REJECT_MATCH','REJECTED_MATCH')]:
            r=self.decide(p,c,decision);self.assertEqual(r.status_code,200,r.text);p=r.json()
            report=self.report(p);latest=next(v for v in report['source_reviews'] if v['candidate_id']==c['id'] and v['is_latest'])
            self.assertEqual(latest['effective_status'],status);self.assertTrue(latest['current'])
            self.assertEqual(latest['reviewed_by'],'local-engineer');self.assertFalse(latest['engineering_approved'])
            self.assertEqual(physical(p['nodes']),physical(before))
            self.assertEqual(p['graph']['edges'],[])
            issues=[i for i in report['issues'] if i.get('evidence_id')==c['id']]
            if decision=='REOPEN':self.assertTrue(any(i['code']=='UNRESOLVED_CONTINUATION_REFERENCE' for i in issues))
            else:self.assertFalse(any(i['code']=='UNRESOLVED_CONTINUATION_REFERENCE' for i in issues))
            if decision=='REJECT_MATCH':self.assertTrue(any(i['code']=='CONTINUATION_ENDPOINT_EXCEPTION' for i in issues))
        decisions=[v['decision'] for v in p['continuation_source_reviews'] if v['candidate_id']==c['id']]
        self.assertEqual(decisions,['ENDPOINT_EXCEPTION','DECLARE_EXTERNAL_BOUNDARY','REOPEN','REJECT_MATCH'])
        p_before=deepcopy(p)
        create_source_exception(p,c,'ACCEPTED_XYZ_REQUIRED','Machine refresh cannot undo an explicit human endpoint decision.')
        self.assertEqual(p,p_before)

    def test_source_point_and_coordinate_edits_stale_a_decision_but_renumber_and_bubbles_do_not(self):
        p=self.model();c=self.candidate(p);p=self.decide(p,c).json()
        self.assertTrue(source_review_states(p)[c['id']]['current'])
        q=deepcopy(p);renumber(q['nodes'])
        for n in q['nodes']:
            for i in n['instances']:i['bubble'][0]+=1
        self.assertTrue(source_review_states(q)[c['id']]['current'])
        for change in ('anchor','source','text','register','coordinate','topology'):
            q=deepcopy(p);point=next(n for n in q['nodes'] if n['id']==c['point_id'])
            if change=='anchor':point['instances'][0]['anchor'][0]+=1
            elif change=='source':next(s for s in q['sheets'] if s['id']==c['sheet_id'])['content_hash']=['changed source']
            elif change=='text':next(v for v in q['automation']['continuation_candidates'] if v['id']==c['id'])['source_text']+=' corrected source text'
            elif change=='register':next(s for s in q['sheets'] if s['id']==c['sheet_id'])['printed_id']='SHEET 9 OF 9'
            elif change=='coordinate':point['coordinates_mm']={'X':'1','Y':None,'Z':None}
            else:point.update(topology_state='ASSIGNED',route='main',order=1)
            with self.subTest(change=change):
                state=source_review_states(q)[c['id']]
                self.assertTrue(state['stale']);self.assertEqual(state['status'],'STALE')
        # Reopen remains available even after source content becomes stale.
        q=deepcopy(p);next(s for s in q['sheets'] if s['id']==c['sheet_id'])['content_hash']=['changed source']
        with main.db() as conn:conn.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(q),q['id']))
        self.assertEqual(self.decide(q,c,'DECLARE_EXTERNAL_BOUNDARY').status_code,409)
        self.assertEqual(self.decide(q,c,'REOPEN').status_code,200)

    def test_revision_roles_unknown_fields_and_empty_evidence_fail_without_mutation(self):
        p=self.model();c=self.candidate(p);before=deepcopy(p['continuation_source_reviews'])
        self.assertEqual(self.decide(p,c,version=p['version']-1).status_code,409)
        self.assertEqual(self.decide(p,c,confirmed=False).status_code,422)
        self.assertEqual(self.decide(p,c,reason_code='GUESS').status_code,422)
        self.assertEqual(self.decide(p,c,evidence=' '*15).status_code,409)
        current=self.client.get(f"/api/v1/projects/{p['id']}").json()
        self.assertEqual(current['continuation_source_reviews'],before)
        with main.db() as conn:conn.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertEqual(self.decide(p,c).status_code,403)

    def test_curated_reference_cannot_be_used_for_another_interface_on_the_same_sheet(self):
        p=self.model();c=self.candidate(p)
        wrong=next(n for n in p['nodes'] if n['instances'][0]['sheet_id']==c['sheet_id'] and n['id']!=c['point_id'])
        peer=next(n for n in p['nodes'] if n['instances'][0]['sheet_id']!=c['sheet_id'])
        r=self.client.post(f"/api/v1/projects/{p['id']}/continuations",json={'version':p['version'],
            'left_point_id':wrong['id'],'right_point_id':peer['id'],'left_size':'8','right_size':'8','decision':'PROPOSE',
            'left_candidate_id':c['id'],'topology_confirmed':True,'confirmed':True,
            'evidence':'SOFTWARE TEST: deliberately wrong same-sheet source interface must be rejected.'})
        self.assertEqual(r.status_code,422,r.text)

    def test_curated_target_cannot_be_bypassed_by_omitting_the_source_reference(self):
        p=self.model();c=self.candidate(p)
        peer=next(n for n in p['nodes'] if n['instances'][0]['sheet_id']!=c['sheet_id'])
        body={'version':p['version'],'left_point_id':c['point_id'],'right_point_id':peer['id'],
            'left_size':'8','right_size':'8','decision':'PROPOSE','topology_confirmed':True,'confirmed':True,
            'evidence':'SOFTWARE TEST: omitting a curated external-line reference cannot bypass its target context.'}
        r=self.client.post(f"/api/v1/projects/{p['id']}/continuations",json=body)
        self.assertEqual(r.status_code,422,r.text)
        body['left_candidate_id']=c['id']
        r=self.client.post(f"/api/v1/projects/{p['id']}/continuations",json=body)
        self.assertEqual(r.status_code,409,r.text)

    def test_same_source_interface_anchor_can_be_corrected_after_explicit_per_sheet_review(self):
        p=self.model()
        left=next(c for c in p['automation']['continuation_candidates'] if c['source_label']=='S1-CONT-SHEET2')
        right=next(c for c in p['automation']['continuation_candidates'] if c['source_label']=='S2-CONT-SHEET1')
        n=next(n for n in p['nodes'] if n['id']==left['point_id'])
        body={k:deepcopy(n.get(k)) for k in ('line_id','route','takeoff_id','order','topology_state','kind','instances','source_feature_id','source_feature_role')}
        body.update(version=p['version'],dimension='',evidence='SOFTWARE TEST: deliberately correct this graphic anchor on the same original source; no engineering coordinates or topology are accepted.')
        body['instances'][0]['anchor'][0]+=.25
        r=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{n['id']}",json=body)
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        compare={'version':p['version'],'left_point_id':left['point_id'],'right_point_id':right['point_id'],
            'left_candidate_id':left['id'],'right_candidate_id':right['id'],'left_size':'8','right_size':'8','decision':'PROPOSE',
            'topology_confirmed':True,'confirmed':True,'evidence':'SOFTWARE TEST: compare only after the corrected source interface location is explicitly reviewed.'}
        self.assertEqual(self.client.post(f"/api/v1/projects/{p['id']}/continuations",json=compare).status_code,409)
        body.update(version=p['version'],source_location_confirmed=True,source_location_sheet_id=left['sheet_id'])
        r=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{n['id']}",json=body)
        self.assertEqual(r.status_code,200,r.text);p=r.json();compare['version']=p['version']
        r=self.client.post(f"/api/v1/projects/{p['id']}/continuations",json=compare)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['continuations'][-1]['status'],'COORDINATE_EVIDENCE_REQUIRED')
        self.assertTrue(all(n['number'] is None and n['station_mm'] is None for n in r.json()['nodes']))


class UnassignedIdentityApiTests(unittest.TestCase):
    """Reuse the existing labelled rule fixture; this is not real 1010 evidence."""
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload
    node=fixtures.ApiTests.node
    model=existing_continuations.ContinuationApiTests.model
    match=existing_continuations.ContinuationApiTests.match

    def store(self,p):
        with main.db() as conn:conn.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p),p['id']))

    def unassign(self,p,index):
        p['nodes'][index].update(topology_state='UNASSIGNED',route=None,order=None,number=None,takeoff_id=None,station_mm=None)

    def test_api_preserves_unassigned_state_when_exact_independent_source_identity_is_accepted(self):
        p=self.model();self.unassign(p,0);self.unassign(p,1);self.store(p)
        r=self.match(p,'ACCEPT_IDENTITY');self.assertEqual(r.status_code,200,r.text)
        p=r.json();self.assertEqual(len(p['nodes']),1)
        n=p['nodes'][0]
        self.assertEqual(len(n['instances']),2)
        self.assertEqual(n['topology_state'],'UNASSIGNED')
        self.assertTrue(all(n[k] is None for k in ('number','route','order','station_mm')))
        self.assertEqual(p['graph']['edges'],[])

    def test_api_selects_the_existing_assigned_identity_even_if_the_unassigned_point_is_chosen_first(self):
        p=self.model();canonical=p['nodes'][0]['id'];self.unassign(p,1);self.store(p)
        r=self.match(p,'ACCEPT_IDENTITY',left_point_id=p['nodes'][1]['id'],right_point_id=canonical)
        self.assertEqual(r.status_code,200,r.text)
        n=r.json()['nodes'][0]
        self.assertEqual(n['id'],canonical);self.assertEqual(n['number'],10)
        self.assertEqual(n['route'],'main');self.assertEqual(n['order'],0)

    def test_api_cannot_accept_a_zero_delta_chain_as_independent_peer_coordinate_evidence(self):
        p=self.model();left,right=[n['id'] for n in p['nodes']]
        p['physical_model']['constraints']=[c for c in p['physical_model']['constraints'] if c['from_point_id']==left]
        from tests.unit.test_physical_model import dimension
        for axis in ('X','Y','Z'):p['physical_model']['constraints'].append(dimension('dependent-'+axis,left,right,'0',axis=axis))
        self.store(p)
        r=self.match(p,'ACCEPT_IDENTITY');self.assertEqual(r.status_code,409,r.text)
        current=self.client.get(f"/api/v1/projects/{p['id']}").json()
        self.assertEqual(current['version'],p['version'])
        self.assertEqual(len(current['nodes']),2)

    def test_api_current_shared_source_rows_show_canonical_identity_and_match_evidence(self):
        from packages.engineering.continuations import source_candidates
        from packages.automation.extract import extract_page
        p=self.model();source=main.DATA/'sources'/f"{p['sheets'][0]['source_id']}.pdf"
        candidates=[]
        for sheet in p['sheets']:candidates.extend(source_candidates(extract_page(source,sheet['page_index'],ocr=False),sheet))
        p['automation']={'continuation_candidates':candidates};self.store(p)
        r=self.match(p,'ACCEPT_IDENTITY',left_candidate_id=candidates[0]['id'],right_candidate_id=candidates[1]['id'])
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        report=self.client.get(f"/api/v1/projects/{p['id']}/continuations").json()
        self.assertTrue(all(c['point_id']==p['nodes'][0]['id'] for c in report['candidates']))
        self.assertTrue(all(v['status']=='SHARED_IDENTITY_REVIEWED' and v['reason_code'] is None and v['evidence']==p['continuations'][-1]['evidence']
                            for v in report['source_review_states'].values()))


class UnassignedIdentityTests(unittest.TestCase):
    def unassigned(self,p,index):
        p['nodes'][index].update(topology_state='UNASSIGNED',route=None,order=None,number=None,takeoff_id=None,
            review_label='P'+str(index+1),station_mm=None,verification='proposed')
        return p['nodes'][index]

    def test_two_unassigned_exact_source_points_merge_without_route_numbers_or_edges(self):
        p=fixture();a=self.unassigned(p,0);b=self.unassigned(p,1)
        self.assertEqual(assess_pair(p,a['id'],b['id'],'8','8')['status'],'EXACT_COORDINATE_MATCH')
        keep=merge_identity(p,a['id'],b['id'])
        self.assertEqual(keep['id'],'left');self.assertEqual(len(keep['instances']),2)
        for key in ('route','order','number','takeoff_id'):self.assertIsNone(keep[key])
        self.assertEqual(keep['topology_state'],'UNASSIGNED')
        self.assertEqual(topology(p['nodes'])['edges'],[])
        self.assertEqual(len(p['physical_model']['constraints']),6)

    def test_assigned_canonical_wins_over_new_unassigned_depiction_in_either_selection_order(self):
        for reverse in (False,True):
            p=fixture();self.unassigned(p,1);renumber(p['nodes']);before=deepcopy(p['nodes'][0])
            keep=merge_identity(p,'right','left') if reverse else merge_identity(p,'left','right')
            self.assertEqual(keep['id'],'left')
            for key in ('route','order','number','station_mm'):self.assertEqual(keep[key],before[key])
            self.assertEqual(topology(p['nodes'])['edges'],[])

    def test_source_observations_and_review_history_stay_independent_after_merge(self):
        p=fixture()
        for i in range(2):
            n=self.unassigned(p,i);sheet=p['sheets'][i]
            n['source_observation']={'id':'source-'+str(i),'sheet_id':sheet['id'],'verification':'reviewed',
                'source_sha256':sheet['sha256'],'content_hash':sheet['content_hash'],
                'review_proof':{'sheet_id':sheet['id'],'anchor':deepcopy(n['instances'][0]['anchor']),
                    'reviewed_by':'EXPLICIT RULE TEST ONLY','evidence':'Generic state-contract fixture, not real 1010 engineering evidence.',
                    'source_sha256':sheet['sha256'],'content_hash':sheet['content_hash']},'review_history':[{'previous':'retained-'+str(i)}]}
        expected=deepcopy([n['source_observation'] for n in p['nodes']])
        keep=merge_identity(p,'left','right')
        self.assertEqual(source_observations(keep),expected)

    def test_a_single_anchor_and_zero_delta_cannot_tautologically_prove_a_match(self):
        p=fixture();p['physical_model']['constraints']=[c for c in p['physical_model']['constraints'] if c['from_point_id']=='left']
        from tests.unit.test_physical_model import dimension
        for axis in ('X','Y','Z'):
            c=dimension('tautology-'+axis,'left','right','0',axis=axis)
            p['physical_model']['constraints'].append(c)
        self.assertEqual(assess_pair(p,'left','right','8','8')['status'],'COORDINATE_EVIDENCE_REQUIRED')

    def test_register_edits_invalidate_an_accepted_identity(self):
        p=fixture();stamps=source_stamp(p,{'left','right'})
        from packages.engineering.continuations import coordinate_proof
        keep=merge_identity(p,'left','right')
        p['continuations']=[{'id':'accepted','status':'ACCEPTED','point_id':keep['id'],'left_point_id':'left','right_point_id':'right',
            'line_id':keep['line_id'],'source_stamps':stamps,'coordinate_proof_sha256':coordinate_proof(p,{keep['id']})}]
        self.assertEqual(identity_audit(p),[])
        p['sheets'][0]['identity_verified']=False
        self.assertEqual(identity_audit(p)[0]['code'],'CONTINUATION_SOURCE_STALE')
        p['sheets'][0]['identity_verified']=True
        keep['line_id']='A DIFFERENT FULL LINE'
        self.assertEqual(identity_audit(p)[0]['code'],'CONTINUATION_SOURCE_STALE')


if __name__=='__main__':unittest.main()
