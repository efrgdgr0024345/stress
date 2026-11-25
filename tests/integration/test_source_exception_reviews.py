"""An actual source exception can be explained/reopened without inventing facts."""
import unittest
from tests.integration import test_api as fixtures
from tests.integration import test_1010_source_review as source_fixtures


class SourceExceptionReviewTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload
    source=source_fixtures.SourceReviewTests.source
    prepare=source_fixtures.SourceReviewTests.prepare

    def test_explanations_and_reopening_do_not_accept_missing_engineering_values(self):
        p=self.prepare(self.source());path=f"/api/v1/projects/{p['id']}/physical-model/source-exceptions"
        response=self.client.get(path);self.assertEqual(response.status_code,200,response.text)
        report=response.json();row=next(v for v in report['all'] if v['code']=='DIMENSION_WITNESS_MAPPING_UNCONFIRMED')
        self.assertIn(row['id'],{v['id'] for v in report['active']})
        body={'version':p['version'],'exception_id':row['id'],'decision':'CONFIRM_WITNESS_MAPPING',
              'evidence':'SOFTWARE VALIDATION: no accepted witness constraint exists, so this must be rejected.',
              'confirmed':True,'constraint_ids':[],'source_context_sha256':row['source_context_sha256']}
        self.assertEqual(self.client.post(path+'/decision',json=body).status_code,422)
        body.update(decision='RETAIN_UNRESOLVED',evidence='SOFTWARE VALIDATION: printed chain is visible but witness endpoints need an engineer to inspect and accept source lengths.')
        response=self.client.post(path+'/decision',json=body);self.assertEqual(response.status_code,200,response.text);p=response.json()
        report=self.client.get(path).json();self.assertIn(row['id'],{v['id'] for v in report['active']})
        self.assertEqual(len(report['reviews']),1)
        self.assertTrue(all(n['station_mm'] is None and n['number'] is None for n in p['nodes']))
        self.assertEqual(p['graph']['edges'],[])
        self.assertFalse(p.get('review_approval'))
        row=next(v for v in report['all'] if v['id']==row['id'])
        body.update(version=p['version'],decision='REOPEN',source_context_sha256=row['source_context_sha256'])
        response=self.client.post(path+'/decision',json=body);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(self.client.get(path).json()['reviews']),2)
        self.assertEqual(self.client.post(path+'/decision',json=body).status_code,409)
