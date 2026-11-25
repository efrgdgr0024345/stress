"""Actual-source dispositions must remain inside the signed geometry scope.

These isolated software reviews do not locate or approve real engineering data.
"""
from copy import deepcopy
import unittest

from packages.physical.source_exceptions import (source_exception_report,
    record_source_exception_decision)
from packages.reviews import scopes
from tests.unit import test_source_exceptions as fixture


class SourceExceptionScopeTests(unittest.TestCase):
    def test_resolved_reference_review_does_not_bind_its_display_number(self):
        p=self.model()
        from packages.engineering.continuations import make_source_review
        candidate=next(c for c in p['automation']['continuation_candidates'] if c.get('source_label')=='S2-CONT-SHEET1')
        p.setdefault('continuation_source_reviews',[]).append(make_source_review(
            p,candidate,'REJECT_MATCH','ACCEPTED_XYZ_REQUIRED',fixture.EVIDENCE,fixture.REVIEWER,fixture.WHEN))
        original=self.geometry(p)
        row=next(r for r in original['payload']['source_exceptions'] if r['code']=='CONTINUATION_INTERFACE_REVIEW_REQUIRED')
        self.assertFalse(row['active'])
        next(n for n in p['nodes'] if n['id']==candidate['point_id'])['number']=170
        self.assertEqual(self.geometry(p)['sha256'],original['sha256'])

    def model(self):
        return fixture.SourceExceptionTests().model()

    def geometry(self,project):
        return next(s for s in scopes(project) if s['kind']=='geometry' and
                    s['key']=='geometry:'+project['line_id'])

    def decide(self,project,entry,decision):
        return record_source_exception_decision(project,entry['id'],decision,
            fixture.EVIDENCE,fixture.REVIEWER,fixture.WHEN,
            source_context_sha256=entry['source_context_sha256'])

    def test_each_active_real_source_exception_is_a_geometry_blocker(self):
        p=self.model();report=source_exception_report(p);scope=self.geometry(p)
        self.assertTrue(report['active'])
        self.assertTrue({r['code'] for r in report['active']}<=set(scope['blocking']))
        self.assertEqual({r['id'] for r in scope['payload']['source_exceptions']},
                         {r['id'] for r in report['all']})
        self.assertTrue(all(r['color']=='blue' and not r['engineering_approved']
                            for r in report['active']))
        # The already corrected source metadata is retained as current proof,
        # not manufactured into a still-active blocker or an approval receipt.
        corrected=next(r for r in report['all'] if r['code']=='SOURCE_INVENTORY_METADATA_CORRECTION_REQUIRED')
        self.assertFalse(corrected['active'])
        self.assertNotIn(corrected['code'],scope['blocking'])
        self.assertTrue(all(n['station_mm'] is None and n['number'] is None for n in p['nodes']))
        self.assertFalse(p.get('review_approval'))

    def test_retain_and_reopen_change_the_signed_scope_without_waiving_missing_facts(self):
        p=self.model();row=next(r for r in source_exception_report(p)['active']
            if r['code']=='DIMENSION_WITNESS_MAPPING_UNCONFIRMED')
        nodes=deepcopy(p['nodes']);physical=deepcopy(p['physical_model'])
        original=self.geometry(p)
        first=self.decide(p,row,'RETAIN_UNRESOLVED');retained=self.geometry(p)
        self.assertNotEqual(original['sha256'],retained['sha256'])
        self.assertIn(row['code'],retained['blocking'])
        stored=next(r for r in retained['payload']['source_exceptions'] if r['id']==row['id'])
        self.assertTrue(stored['active']);self.assertEqual(stored['status'],'RETAINED_UNRESOLVED')
        self.assertTrue(stored['latest_review']['current'])
        second=self.decide(p,stored,'REOPEN');reopened=self.geometry(p)
        self.assertNotEqual(retained['sha256'],reopened['sha256'])
        self.assertIn(row['code'],reopened['blocking'])
        history=[r for r in reopened['payload']['source_exception_reviews'] if r['exception_id']==row['id']]
        self.assertEqual([r['id'] for r in history],[first['id'],second['id']])
        self.assertEqual([r['is_latest'] for r in history],[False,True])
        self.assertTrue(all(not r['engineering_approved'] for r in history))
        self.assertEqual(p['nodes'],nodes);self.assertEqual(p['physical_model'],physical)
        self.assertFalse(p.get('review_approval'))

    def test_geometry_scope_ignores_bubbles_and_numbers_but_binds_source_anchors(self):
        p=self.model();row=next(r for r in source_exception_report(p)['active']
            if r['code']=='DASHED_BOUNDARY_INTERFACE_REVIEW_REQUIRED')
        self.decide(p,row,'RETAIN_UNRESOLVED')
        original=self.geometry(p)
        layouts={s['key']:s['sha256'] for s in scopes(p) if s['kind']=='layout'}
        point=next(n for n in p['nodes'] if n['id'] in row['point_ids'])
        point['number']=170
        point['instances'][0]['bubble'][0]+=20
        displayed=self.geometry(p)
        self.assertEqual(displayed['sha256'],original['sha256'])
        self.assertNotEqual({s['key']:s['sha256'] for s in scopes(p) if s['kind']=='layout'},layouts)
        point['instances'][0]['anchor'][0]+=1
        moved=self.geometry(p)
        self.assertNotEqual(moved['sha256'],original['sha256'])
        source=next(r for r in moved['payload']['source_exceptions'] if r['id']==row['id'])
        self.assertTrue(source['active']);self.assertEqual(source['color'],'blue')
        self.assertTrue(source['latest_review']['stale'])
        self.assertIn(source['code'],moved['blocking'])
