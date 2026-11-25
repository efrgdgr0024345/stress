"""Source N/A explanations are part of the actual drawing's review scope."""
import unittest
from packages.catalogs.project_review import (prepare_catalog_review,record_catalog_decision,
    refresh_project_catalog_reviews,catalog_review_report)
from packages.reviews import scopes
from tests.unit import test_source_exceptions as fixtures


class CatalogScopeTests(unittest.TestCase):
    def test_revised_na_explanation_invalidates_material_signoff_without_accepting_data(self):
        p=fixtures.SourceExceptionTests().model()
        prepare_catalog_review(p,[],fixtures.REVIEWER,fixtures.WHEN)
        row=catalog_review_report(p,[])['rows'][0]
        def explain(text):
            record_catalog_decision(p,[],row['material_id'],'DECLARE_NA','NO_EXACT_CATALOG_MATCH',
                text,fixtures.REVIEWER,fixtures.WHEN,row['source_context_sha256'])
            refresh_project_catalog_reviews(p,[])
            return next(s for s in scopes(p) if s['key']=='materials:'+row['sheet_id'])
        before=explain('SOFTWARE VALIDATION: source applicability is not proved; keep unknown project weights N/A.')
        after=explain('SOFTWARE VALIDATION revised explanation: obtain exact facing, bore and flange type evidence before accepting values.')
        self.assertNotEqual(before['sha256'],after['sha256'])
        self.assertEqual(len(after['payload']['catalog_reviews']),2)
        current=next(r for r in catalog_review_report(p,[])['rows'] if r['material_id']==row['material_id'])
        self.assertEqual(current['status'],'DECLARED_NA')
        self.assertTrue(all(v is None for v in current['values'].values()))
        self.assertEqual(current['project_manufacturer']['status'],'UNCONFIRMED')
        self.assertTrue(all(n['station_mm'] is None and n['number'] is None for n in p['nodes']))
        self.assertFalse(p.get('review_approval'))
