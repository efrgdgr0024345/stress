"""Station review workflow on the exact real PDF, in disposable software projects."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import unittest
from packages.physical.stations import solve_stations
from tests.integration import test_api as fixtures

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'


class StationApiTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    upload=fixtures.ApiTests.upload

    def source(self):
        r=self.client.post('/api/v1/projects',json={'title':'SOFTWARE ONLY actual 1010 station review contract','line_id':'8-PG-JE3LN2-1010-FUTURE'})
        self.assertEqual(r.status_code,201,r.text)
        p=self.upload(r.json(),SOURCE.read_bytes())
        r=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/source-points",json={'version':p['version'],'confirmed':True})
        self.assertEqual(r.status_code,200,r.text)
        p=r.json();report=self.report(p)
        self.assertEqual(len(report['proposals']),4)
        proposal=next((v for v in report['proposals'] if v['source_text']=='2"'),report['proposals'][0])
        return p,proposal

    def path(self,p):return f"/api/v1/projects/{p['id']}/physical-model/stations"
    def report(self,p):
        r=self.client.get(self.path(p));self.assertEqual(r.status_code,200,r.text);return r.json()

    def add(self,p,proposal,kind='DELTA',**changes):
        body={'version':p['version'],'kind':kind,'from_point_id':proposal['from_point_id'],
            'to_point_id':proposal['to_point_id'] if kind=='DELTA' else None,
            'source_text':proposal['source_text'] if kind=='DELTA' else '0 mm',
            'source_format':proposal['source_format'] if kind=='DELTA' else 'STANDARD','tolerance_text':'0 mm',
            'distance_basis':'ALONG_CENTRELINE','sheet_id':proposal['sheet_id'],
            'evidence':'SOFTWARE VALIDATION of actual source '+proposal['source_text']+'; explicit scalar source direction/local datum only, no surveyed station or engineering approval.',
            'confirmed':True}
        if kind=='DELTA':body['source_proposal_id']=proposal['id']
        body.update(changes)
        return self.client.post(self.path(p)+'/constraints',json=body)

    def assign(self,p,ids):
        for index,point in enumerate(ids):
            n=next(n for n in p['nodes'] if n['id']==point)
            body={k:deepcopy(n.get(k)) for k in ('line_id','kind','instances','source_feature_id','source_feature_role')}
            body.update(version=p['version'],route='main',order=index,topology_state='ASSIGNED',topology_confirmed=True,
                source_location_confirmed=True,source_location_sheet_id=n['instances'][0]['sheet_id'],dimension='',
                evidence='SOFTWARE VALIDATION ONLY: inspected this actual source support point; explicit disposable pair-only route order, unknown station and no lead-engineer approval.')
            r=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{point}",json=body)
            self.assertEqual(r.status_code,200,r.text);p=r.json()
        return p

    def test_real_source_chain_needs_topology_then_explicit_origin_and_explicit_apply(self):
        p,proposal=self.source();ids=(proposal['from_point_id'],proposal['to_point_id'])
        r=self.add(p,proposal);self.assertEqual(r.status_code,200,r.text);p=r.json()
        report=self.report(p)
        self.assertFalse(report['solution']['can_apply'])
        self.assertTrue(all(n['station_mm'] is None for n in p['nodes']))
        self.assertTrue(all(v['status']=='TOPOLOGY_REQUIRED' for v in report['solution']['points'] if v['point_id'] in ids))
        p=self.assign(p,ids);report=self.report(p)
        self.assertFalse(report['solution']['can_apply'])
        self.assertTrue(all(v['status']=='RELATIVE_ONLY' for v in report['solution']['points'] if v['point_id'] in ids))
        self.assertEqual(self.client.post(self.path(p)+'/apply',json={'version':p['version'],'reason':'No origin has been deliberately chosen; this must fail without moving a station.','confirmed':True}).status_code,409)
        r=self.add(p,proposal,'LOCAL_ORIGIN');self.assertEqual(r.status_code,200,r.text);p=r.json()
        report=self.report(p);self.assertTrue(report['solution']['can_apply'])
        self.assertTrue(all(n['station_mm'] is None for n in p['nodes']))
        r=self.client.post(self.path(p)+'/apply',json={'version':p['version'],
            'reason':'SOFTWARE VALIDATION: accept the actual printed support gap with an explicitly chosen relative local datum; no absolute surveyed station or engineering model approval.',
            'point_ids':list(ids),'confirmed':True})
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        nodes={n['id']:n for n in p['nodes']};a,b=(nodes[v] for v in ids)
        self.assertEqual(Decimal(a['station_mm']),0)
        self.assertEqual(Decimal(b['station_mm']),Decimal(proposal['proposed_distance_mm']))
        self.assertIn('SUPPORT_WITHIN_6_IN',b['reasons'])
        self.assertEqual(a['station_proof']['basis'],'LOCAL_ORIGIN')
        self.assertEqual(a['station_proof']['basis_id'],b['station_proof']['basis_id'])
        self.assertTrue(all(n['station_mm'] is None for n in p['nodes'] if n['id'] not in ids))
        self.assertFalse(any(i['code']=='STATION_SOLUTION_STALE' for i in self.report(p)['solution']['issues']))
        # A new explicit apply is idempotent, never a feedback anchor.
        r=self.client.post(self.path(p)+'/apply',json={'version':p['version'],'reason':'SOFTWARE VALIDATION: reapply the same current station proof without feeding back derived outputs.','point_ids':list(ids),'confirmed':True})
        self.assertEqual(r.status_code,200,r.text)
        self.assertFalse(any(i['code']=='STATION_SOLUTION_STALE' for i in self.report(r.json())['solution']['issues']))

    def test_source_formats_and_published_proposal_lengths_are_checked_without_guessing(self):
        p,proposal=self.source()
        for source in ('E 2 in','N 2 in','S 2 in','EL 2 in','X 2 in'):
            with self.subTest(source=source):self.assertEqual(self.add(p,proposal,source_text=source,source_format='STANDARD').status_code,422)
        self.assertEqual(self.add(p,proposal,source_text='3 in',source_format='STANDARD').status_code,422)
        self.assertEqual(self.add(p,proposal,'LOCAL_ORIGIN',source_text='1 mm').status_code,422)
        self.assertEqual(self.add(p,proposal,confirmed=False).status_code,422)
        self.assertEqual(self.add(p,proposal,version=p['version']-1).status_code,409)
        dots=next(v for v in self.report(p)['proposals'] if v['source_format']=='ISO_IN_DOT_FRACTION')
        r=self.add(p,dots);self.assertEqual(r.status_code,200,r.text);p=r.json()
        c=p['physical_model']['station_constraints'][-1]
        self.assertEqual(c['source_text'],dots['source_text']);self.assertEqual(c['source_format'],'ISO_IN_DOT_FRACTION')
        self.assertEqual(Decimal(c['value_mm']),Decimal(dots['proposed_distance_mm']))
        self.assertTrue(all(n['station_mm'] is None for n in p['nodes']))

    def test_constraint_edit_and_withdrawal_keep_old_station_values_until_reviewed_apply(self):
        p,proposal=self.source();ids=(proposal['from_point_id'],proposal['to_point_id']);p=self.assign(p,ids)
        p=self.add(p,proposal).json();p=self.add(p,proposal,'LOCAL_ORIGIN').json()
        r=self.client.post(self.path(p)+'/apply',json={'version':p['version'],'reason':'SOFTWARE VALIDATION: explicitly accept the current source chain and local station basis.','confirmed':True})
        self.assertEqual(r.status_code,200,r.text);p=r.json();old={n['id']:n['station_mm'] for n in p['nodes']}
        delta=next(c for c in p['physical_model']['station_constraints'] if c['kind']=='DELTA')
        # Same printed length, deliberate direction reversal, accepted source text retained.
        body={k:deepcopy(delta.get(k)) for k in ('kind','from_point_id','to_point_id','source_text','source_format','tolerance_text','evidence','sheet_id','distance_basis','source_proposal_id')}
        body.update(version=p['version'],source_text='-'+delta['source_text'],confirmed=True)
        r=self.client.patch(self.path(p)+'/constraints/'+delta['id'],json=body)
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        self.assertEqual({n['id']:n['station_mm'] for n in p['nodes']},old)
        self.assertTrue(any(i['code']=='STATION_SOLUTION_STALE' for i in self.report(p)['solution']['issues']))
        r=self.client.request('DELETE',self.path(p)+'/constraints/'+delta['id'],json={'version':p['version'],
            'reason':'SOFTWARE VALIDATION: withdraw this source-direction choice and retain the earlier applied value for review.','confirmed':True})
        self.assertEqual(r.status_code,200,r.text);p=r.json()
        self.assertEqual({n['id']:n['station_mm'] for n in p['nodes']},old)
        self.assertTrue(p['physical_model']['retired_station_constraints'])
        self.assertIn('STATION_SOLUTION_STALE',next(n for n in p['nodes'] if n['id']==ids[1])['reasons'])

    def test_partial_apply_rejects_an_unknown_selected_point_atomically_and_viewers_cannot_edit(self):
        p,proposal=self.source();ids=(proposal['from_point_id'],proposal['to_point_id']);p=self.assign(p,ids)
        p=self.add(p,proposal).json();p=self.add(p,proposal,'LOCAL_ORIGIN').json()
        unknown=next(n['id'] for n in p['nodes'] if n['id'] not in ids)
        r=self.client.post(self.path(p)+'/apply',json={'version':p['version'],'point_ids':[ids[0],unknown],
            'reason':'SOFTWARE VALIDATION: a mixed solved/unknown selection must fail without changing either point.','confirmed':True})
        self.assertEqual(r.status_code,409,r.text)
        current=self.client.get(f"/api/v1/projects/{p['id']}").json()
        self.assertEqual(current['version'],p['version']);self.assertTrue(all(n['station_mm'] is None for n in current['nodes']))
        with fixtures.main.db() as connection:connection.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertEqual(self.add(p,proposal).status_code,403)
