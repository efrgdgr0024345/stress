import hashlib
import json
import unittest
from unittest.mock import patch
from services.api import main, remote_setup, digitalocean as provider
from services.api.updates import write
from tests.integration import test_api as fixtures
from tests.integration.test_digitalocean import NAMESPACE, TOKEN


class RemoteSetupTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown

    def connected(self):
        write(provider.directory(main.DATA)/'credentials.json',{'token':TOKEN,'verified_at':1})

    def test_enabling_queues_setup_outside_passenger_and_requires_hosting_operator(self):
        self.connected()
        with patch.object(provider,'request') as request:
            response=self.client.post('/api/v1/system/digitalocean/processing',json={'enabled':True})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['worker']['state'],'queued')
            self.assertFalse(request.called)
        self.assertAlmostEqual(response.json()['maximum_compute_usd_per_month_before_allowance'],2.22)
        with main.db() as c:c.execute("UPDATE users SET role='engineer' WHERE id='local-engineer'")
        self.assertEqual(self.client.post('/api/v1/system/digitalocean/processing',json={'enabled':False}).status_code,403)
        self.assertEqual(self.client.get('/api/v1/system/digitalocean/processing').status_code,403)

    def test_setup_fetches_private_details_and_deploys_bounded_non_web_action_without_exposing_keys(self):
        self.connected()
        self.client.post('/api/v1/system/digitalocean/processing',json={'enabled':True})
        def build(path):
            path.mkdir();(path/'extract.zip').write_bytes(b'synthetic-function')
            write(path/'build-report.json',{'zip_sha256':hashlib.sha256(b'synthetic-function').hexdigest()})
        with patch('scripts.build_functions_demo.build',side_effect=build):self.assertTrue(remote_setup.advance(main))
        label='caesar-demo-'+hashlib.sha256(str(main.DATA.resolve()).encode()).hexdigest()[:10]
        ns={**NAMESPACE,'label':label,'region':'syd1'}
        with patch.object(provider,'request',side_effect=[{'namespaces':[{**ns,'uuid':'','key':''}]},{'namespace':ns}]):
            self.assertTrue(remote_setup.advance(main))
        with patch.object(provider,'namespace_api',return_value={}) as deploy:
            self.assertTrue(remote_setup.advance(main))
            action=deploy.call_args.args[3]
            self.assertFalse(action['publish']);self.assertEqual(action['limits']['memory'],1024)
            self.assertEqual(action['limits']['timeout'],240000)
            self.assertEqual(action['annotations'],[{'key':'web-export','value':False}])
            self.assertNotIn(TOKEN,json.dumps(action))
        public=self.client.get('/api/v1/system/digitalocean/processing').json()
        self.assertEqual(public['worker']['state'],'ready')
        self.assertFalse((remote_setup.directory(main.DATA)/'build').exists())
        self.assertNotIn(TOKEN,json.dumps(public));self.assertNotIn(NAMESPACE['key'],json.dumps(public))
        with patch.object(provider,'namespace_api') as request:
            self.assertFalse(remote_setup.advance(main));self.assertFalse(request.called)
        with patch.object(remote_setup,'version',return_value='a'*64):
            remote_setup.ensure(main)
        self.assertEqual(remote_setup.status(main.DATA)['state'],'queued')

    def test_disabled_policy_makes_no_provider_calls_and_failed_setup_remains_visible(self):
        with patch.object(provider,'request') as request:
            self.assertFalse(remote_setup.advance(main));self.assertFalse(request.called)
        self.connected()
        self.client.post('/api/v1/system/digitalocean/processing',json={'enabled':True})
        with patch('scripts.build_functions_demo.build',side_effect=ValueError('PRIVATE_UPSTREAM_SENTINEL')):
            remote_setup.advance(main)
        response=self.client.get('/api/v1/system/digitalocean/processing')
        self.assertEqual(response.json()['worker']['state'],'failed')
        self.assertNotIn('PRIVATE_UPSTREAM_SENTINEL',response.text+self.client.get('/api/v1/system/logs/export').text)
