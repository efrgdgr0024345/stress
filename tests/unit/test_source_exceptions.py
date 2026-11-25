"""Actual reviewed-source exceptions; isolated test reviews are not engineering approval."""
from copy import deepcopy
from pathlib import Path
import hashlib
import unittest
from unittest.mock import patch

from packages.pdf import inspect_pdf
from packages.physical.source_review import prepare_source_points,source_profile
from packages.physical.source_exceptions import (source_exception_report,refresh_source_exceptions,
    record_source_exception_decision)
from packages.physical.stations import source_stamps
from packages.engineering.coordinates import coordinate_value

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'
REVIEWER='SOFTWARE-ONLY-TEST-REVIEWER'
WHEN='2026-11-25T00:00:00+00:00'
EVIDENCE='SOFTWARE TEST ONLY: explicit source disposition, not real engineering acceptance.'


class SourceExceptionTests(unittest.TestCase):
    def model(self):
        sha=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        p={'id':'SOFTWARE-ONLY-real-source-exceptions','version':1,'line_id':'8-PG-JE3LN2-1010-FUTURE',
           'nodes':[],'materials':[],'sheets':[],'annotations':[],'engineering_approved':False}
        for index,raw in enumerate(inspect_pdf(SOURCE)):
            p['sheets'].append({**raw,'id':f'software-source-sheet-{index}','page_index':index,'source_id':'software-source',
                               'sha256':sha,'line_id':p['line_id'],'printed_id':'','filename':SOURCE.name})
        prepare_source_points(p)
        return p

    def row(self,p,code,**filters):
        return next(r for r in source_exception_report(p)['all'] if r['code']==code and all(r.get(k)==v for k,v in filters.items()))

    def decide(self,p,row,decision,**changes):
        return record_source_exception_decision(p,row['id'],decision,EVIDENCE,REVIEWER,WHEN,
            source_context_sha256=row['source_context_sha256'],**changes)

    def test_real_profile_station_and_cod_requirements_are_finishable_not_silently_dropped(self):
        p=self.model();report=source_exception_report(p)
        cod=[r for r in report['active'] if r['code']=='UNCONFIRMED_ELBOW_COD']
        self.assertEqual(len(cod),5)
        self.assertEqual(len({r['id'] for r in report['all']}),len(report['all']))
        station_ids={r['id'] for r in source_profile()['station_source_facts']['exceptions']}
        self.assertEqual({r['source_exception_id'] for r in report['all'] if r['source_group']=='STATION_DIMENSION'},station_ids)
        self.assertTrue(all(r['color']=='blue' and r['source_current'] and not r['engineering_approved'] for r in report['active']))
        fixed=self.row(p,'SOURCE_INVENTORY_METADATA_CORRECTION_REQUIRED')
        self.assertFalse(fixed['active']);self.assertEqual(fixed['resolution']['method'],'CURRENT_SOURCE_METADATA_PRESENT')
        self.assertTrue(all(n['station_mm'] is None for n in p['nodes']))
        self.assertEqual(p.get('physical_model',{}).get('constraints'),[])
        self.assertFalse(report['engineering_approved'])

    def test_pv_classification_needs_actual_current_human_classification_evidence(self):
        p=self.model();row=self.row(p,'INSTRUMENT_CLASSIFICATION_REVIEW_REQUIRED');self.assertTrue(row['active'])
        self.assertEqual(len(row['point_ids']),2)
        self.assertTrue(all(row['code'] in n.get('source_exception_reasons',[]) for n in p['nodes'] if n['id'] in row['point_ids']))
        material=next(m for m in p['materials'] if m['id']==row['material_id'])
        material['family']='valve'
        self.assertTrue(self.row(p,row['code'])['active'])
        material.update(verification='reviewed',evidence='')
        self.assertTrue(self.row(p,row['code'])['active'])
        material['evidence']=EVIDENCE
        resolved=self.row(p,row['code']);self.assertFalse(resolved['active'])
        self.assertEqual(resolved['resolution']['method'],'CURRENT_HUMAN_COMPONENT_CLASSIFICATION')
        refresh_source_exceptions(p)
        self.assertTrue(all(row['code'] not in n.get('source_exception_reasons',[]) for n in p['nodes'] if n['id'] in row['point_ids']))
        material['verification']='proposed'
        self.assertTrue(self.row(p,row['code'])['active'])

    def test_coincidence_reasons_bind_only_the_actual_upper_pair_not_all_supports(self):
        p=self.model();row=self.row(p,'COINCIDENT_SUPPORT_REVIEW_REQUIRED')
        self.assertEqual(len(row['point_ids']),2)
        labels={n['source_observation']['source_label'] for n in p['nodes'] if n['id'] in row['point_ids']}
        self.assertEqual(labels,{'S2-S13-UPPER','S2-S14'})
        for n in p['nodes']:
            self.assertEqual(row['code'] in n.get('source_exception_reasons',[]),n['id'] in row['point_ids'])

    def test_documenting_an_exception_never_waives_cod_or_changes_model_facts(self):
        p=self.model();row=self.row(p,'UNCONFIRMED_ELBOW_COD');nodes=deepcopy(p['nodes']);model=deepcopy(p['physical_model'])
        with self.assertRaises(ValueError):self.decide(p,row,'CONFIRM_WITNESS_MAPPING',constraint_ids=[])
        self.assertNotIn('source_exception_reviews',p)
        self.decide(p,row,'RETAIN_UNRESOLVED')
        after=self.row(p,row['code'],occurrence=row['occurrence'],sheet_id=row['sheet_id'],material_item_no=row['material_item_no'])
        self.assertTrue(after['active']);self.assertEqual(after['status'],'RETAINED_UNRESOLVED')
        self.assertTrue(after['latest_review']['current'])
        self.assertEqual(p['nodes'],nodes);self.assertEqual(p['physical_model'],model)
        self.decide(p,after,'REOPEN')
        report=source_exception_report(p)
        self.assertEqual(len(report['reviews']),2);self.assertTrue(report['reviews'][-1]['is_latest'])
        self.assertFalse(report['reviews'][0]['is_latest'])

    def test_source_disposition_context_excludes_presentation_but_binds_anchor_and_source(self):
        p=self.model();row=self.row(p,'DASHED_BOUNDARY_INTERFACE_REVIEW_REQUIRED')
        self.decide(p,row,'RETAIN_UNRESOLVED')
        node=next(n for n in p['nodes'] if n['id'] in row['point_ids'])
        node['number']=170;node['instances'][0]['bubble'][0]+=20
        after=self.row(p,row['code'])
        self.assertEqual(after['source_context_sha256'],row['source_context_sha256']);self.assertTrue(after['latest_review']['current'])
        node['instances'][0]['anchor'][0]+=1
        after=self.row(p,row['code']);self.assertTrue(after['active']);self.assertTrue(after['latest_review']['stale'])
        with self.assertRaises(ValueError):self.decide(p,row,'REOPEN')
        refresh_source_exceptions(p)
        sheet=next(s for s in p['sheets'] if s['id']==row['sheet_id']);sheet['sha256']='a'*64
        stale=self.row(p,row['code']);self.assertEqual(stale['status'],'SOURCE_STALE');self.assertTrue(stale['active'])

    def station_mapping(self,p):
        row=next(r for r in source_exception_report(p)['all'] if r['code']=='DIMENSION_WITNESS_MAPPING_UNCONFIRMED' and r['source_text']=='4\'8.3/8"')
        profile=source_profile();observations={o['source_label']:o for o in profile['observations']}
        bindings=p['source_review']['observation_points']
        a=bindings[observations['S1-FE7681-IN']['id']];b=bindings[observations['S1-FE7681-OUT']['id']]
        sheet=next(s for s in p['sheets'] if s['id']==row['sheet_id'])
        value=coordinate_value(row['source_text'],'X','ISO_FT_IN_DOT_FRACTION')['value_mm']
        c={'id':'SOFTWARE-ONLY-source-delta','kind':'DELTA','from_point_id':a,'to_point_id':b,'source_text':row['source_text'],
           'source_format':'ISO_FT_IN_DOT_FRACTION','value_mm':value,'tolerance_mm':'0','distance_basis':'ALONG_CENTRELINE',
           'sheet_id':sheet['id'],'source_sha256':sheet['sha256'],'source_content_hash':sheet['content_hash'],
           'source_point_stamps':source_stamps(p,{a,b}),'verification':'reviewed','reviewed_by':REVIEWER,'reviewed_at':WHEN,'evidence':EVIDENCE}
        p['physical_model']['station_constraints']=[c]
        return row,c

    def test_witness_disposition_requires_exact_current_accepted_source_delta(self):
        p=self.model();row,c=self.station_mapping(p);before=deepcopy(p['nodes'])
        actual=c['value_mm'];c['value_mm']='1'
        with self.assertRaises(ValueError):self.decide(p,row,'CONFIRM_WITNESS_MAPPING',constraint_ids=[c['id']])
        c['value_mm']=actual;c['verification']='proposed'
        with self.assertRaises(ValueError):self.decide(p,row,'CONFIRM_WITNESS_MAPPING',constraint_ids=[c['id']])
        c['verification']='reviewed';self.decide(p,row,'CONFIRM_WITNESS_MAPPING',constraint_ids=[c['id']])
        after=next(r for r in source_exception_report(p)['all'] if r['id']==row['id'])
        self.assertFalse(after['active']);self.assertEqual(after['resolution']['method'],'EXPLICIT_CURRENT_SOURCE_WITNESS_MAPPING')
        self.assertEqual(p['nodes'],before);self.assertTrue(all(n['station_mm'] is None for n in p['nodes']))
        point=next(n for n in p['nodes'] if n['id']==c['from_point_id']);point['instances'][0]['bubble'][0]+=10
        self.assertFalse(next(r for r in source_exception_report(p)['all'] if r['id']==row['id'])['active'])
        point['instances'][0]['anchor'][0]+=1
        stale=next(r for r in source_exception_report(p)['all'] if r['id']==row['id'])
        self.assertTrue(stale['active']);self.assertTrue(stale['latest_review']['stale'])

    def test_cod_resolution_requires_full_source_convention_and_all_xyz_predicates(self):
        # This is an isolated predicate double, not a real COD location/model.
        # Real source nodes are deliberately left unchanged and all five remain
        # unlocated in the ordinary fixture above.
        p=self.model();row=self.row(p,'UNCONFIRMED_ELBOW_COD');point={'id':'SOFTWARE-ONLY-COD-PROOF-DOUBLE','kind':'elbow'}
        from packages.physical.cod import CONVENTION
        proof={'kind':'DIMENSION_CHAIN_COD','dimension_convention':'SOFTWARE ONLY explicit theoretical centreline intersection proof',
               'dimension_convention_kind':CONVENTION}
        xyz={'schema':'signed-xyz-1','coordinates':[{'point_id':point['id'],'axes':{axis:{'value_mm':'0'} for axis in ('X','Y','Z')}}],
             'issues':[],'inputs':[],'evidence_groups':{},'elements':[],'input_sha256':'SOFTWARE-ONLY-proof-double'}
        with patch('packages.physical.source_exceptions._port_proof',return_value=(point,proof)),patch('packages.physical.constraints.solve',return_value=xyz):
            after=next(r for r in source_exception_report(p)['all'] if r['id']==row['id'])
            self.assertFalse(after['active']);self.assertEqual(after['resolution']['method'],'CURRENT_THEORETICAL_COD_SOURCE_AND_XYZ_PROOF')
            xyz['coordinates'][0]['axes']['Z']['value_mm']=None
            self.assertTrue(next(r for r in source_exception_report(p)['all'] if r['id']==row['id'])['active'])
            xyz['coordinates'][0]['axes']['Z']['value_mm']='0';proof.pop('dimension_convention_kind')
            self.assertTrue(next(r for r in source_exception_report(p)['all'] if r['id']==row['id'])['active'])
        self.assertEqual(len([r for r in source_exception_report(p)['active'] if r['code']=='UNCONFIRMED_ELBOW_COD']),5)

    def test_current_reviewed_peer_rejection_handles_static_ambiguity_but_retains_blue_boundary(self):
        p=self.model();row=self.row(p,'CONTINUATION_INTERFACE_REVIEW_REQUIRED')
        self.assertTrue(row['active'])
        from packages.engineering.continuations import make_source_review,audit
        candidate=next(c for c in p['automation']['continuation_candidates'] if c.get('source_label')=='S2-CONT-SHEET1')
        record=make_source_review(p,candidate,'REJECT_MATCH','ACCEPTED_XYZ_REQUIRED',EVIDENCE,REVIEWER,WHEN)
        p.setdefault('continuation_source_reviews',[]).append(record)
        after=self.row(p,row['code'])
        self.assertFalse(after['active']);self.assertFalse(after['resolution']['physical_identity_accepted'])
        self.assertTrue(any(i['code']=='CONTINUATION_ENDPOINT_EXCEPTION' and i['evidence_id']==candidate['id'] for i in audit(p)))
        self.assertNotIn('point_aliases',p)
        node=next(n for n in p['nodes'] if n['id']==candidate['point_id'])
        node['instances'][0]['bubble'][0]+=10
        self.assertFalse(self.row(p,row['code'])['active'])
        node['instances'][0]['anchor'][0]+=1
        self.assertTrue(self.row(p,row['code'])['active'])

    def test_station_closure_rechecks_fresh_source_issues_instead_of_cached_colour(self):
        p=self.model();node=deepcopy(p['nodes'][0])
        # Predicate double only: an explicitly supplied software-test local
        # datum is not an accepted station in the actual reviewed project.
        node.update(station_mm='0',station_review_reasons=[])
        solution={'points':[{'point_id':node['id'],'can_apply':True,'basis_id':'SOFTWARE-ONLY-local-datum','station_mm':'0'}],
                  'issues':[{'code':'STATION_SOURCE_STALE','point_ids':[node['id']]}]}
        from packages.physical.source_exceptions import _current_station
        with patch('packages.physical.stations.solve_stations',return_value=solution):
            self.assertIsNone(_current_station(p,node,{}))
            solution['issues']=[]
            self.assertIsNotNone(_current_station(p,node,{}))
            solution['issues']=[{'code':'STATION_SOLUTION_STALE','point_ids':[node['id']]}]
            self.assertIsNone(_current_station(p,node,{}))
        self.assertTrue(all(n['station_mm'] is None for n in p['nodes']))
