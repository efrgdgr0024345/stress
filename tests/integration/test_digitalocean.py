"""Provider boundaries, credential privacy and a complete durable demo run."""
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from packages.automation.extract import extract_page
from services.api import main, digitalocean as provider
from services.api.updates import write, read
from tests.integration import test_api as fixtures

TOKEN = 'dop_v1_PRIVATE_TEST_ONLY_SENTINEL_1234567890'
NAMESPACE = {'api_host': 'https://faas-syd1-test.doserverless.co',
             'namespace': 'fn-11111111-1111-4111-8111-111111111111',
             'uuid': '11111111-1111-4111-8111-111111111111', 'key': 'PRIVATE_NAMESPACE_KEY_TEST_ONLY'}


class DigitalOceanTests(unittest.TestCase):
    setUp = fixtures.ApiTests.setUp
    tearDown = fixtures.ApiTests.tearDown
    create = fixtures.ApiTests.create
    upload = fixtures.ApiTests.upload
    pdf = fixtures.ApiTests.pdf

    def connect(self):
        with patch.object(provider, 'request', return_value={'namespaces': []}):
            response = self.client.post('/api/v1/system/digitalocean', json={'token': TOKEN})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_credentials_owner_only_never_returned_or_logged_and_failed_rotation_preserves_old(self):
        self.connect()
        path = provider.directory(main.DATA) / 'credentials.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(read(path)['token'], TOKEN)
        with patch.object(provider, 'request', side_effect=provider.ProviderError('PROVIDER_HTTP_403')):
            response = self.client.post('/api/v1/system/digitalocean', json={'token': TOKEN + '_REPLACE'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(read(path)['token'], TOKEN)
        invalid = self.client.post('/api/v1/system/digitalocean', json={'token': TOKEN, 'unexpected': TOKEN})
        self.assertEqual(invalid.status_code, 422)
        huge = self.client.post('/api/v1/system/digitalocean', json={'token': TOKEN * 100})
        self.assertEqual(huge.status_code, 413)
        text = self.client.get('/api/v1/system/digitalocean').text + response.text + invalid.text
        text += self.client.get('/api/v1/system/logs/export').text
        self.assertNotIn(TOKEN, text)
        self.assertEqual(self.client.delete('/api/v1/system/digitalocean').status_code, 200)
        self.assertFalse(path.exists())

    def test_operator_permission_checked_before_reading_credentials(self):
        self.assertEqual(TestClient(main.app).get('/api/v1/system/digitalocean').status_code, 401)
        with main.db() as conn:
            conn.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        with patch.object(provider, 'save') as save:
            self.assertEqual(self.client.post('/api/v1/system/digitalocean', json={'token': TOKEN}).status_code, 403)
            self.assertEqual(self.client.get('/api/v1/system/digitalocean').status_code, 403)
            self.assertEqual(self.client.delete('/api/v1/system/digitalocean').status_code, 403)
            self.assertFalse(save.called)
        with main.db() as conn:
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", ('tenant-admin', 'Other', 'other@example.invalid', '', 'admin', 'other'))
            conn.execute("UPDATE sessions SET user_id='tenant-admin'")
        with patch.object(main, 'LOCAL_DEMO', False):
            self.assertEqual(self.client.get('/api/v1/system/digitalocean').status_code, 403)

    def test_empty_account_null_namespace_list_is_valid_but_missing_or_invalid_list_is_rejected(self):
        with patch.object(provider, 'request', return_value={'namespaces': None}):
            result = self.client.post('/api/v1/system/digitalocean', json={'token': TOKEN})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()['configured'])
        for invalid in ({}, {'namespaces': {}}, {'namespaces': ['bad']}):
            with patch.object(provider, 'request', return_value=invalid):
                result = self.client.post('/api/v1/system/digitalocean', json={'token': TOKEN + '_NEW'})
            self.assertEqual(result.status_code, 422)
            self.assertEqual(provider.credentials(main.DATA)['token'], TOKEN)
        report = self.client.get('/api/v1/system/logs/export').json()
        check = next(e for e in report['events'] if e['event'] == 'provider.namespaces.checked')
        self.assertTrue(check['details']['empty_list_was_null'])

    def test_provider_http_diagnostics_include_safe_shape_status_and_request_id_without_response_values(self):
        class Response:
            status = 200
            headers = {'Content-Type': 'application/json; charset=utf-8', 'X-Request-Id': 'b939eebf-3cc7-4fea-9b65-2502fa067ead'}
            def read(self, limit):
                return json.dumps({'namespaces': None, 'key': TOKEN, 'unexpected': TOKEN}).encode()
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with patch.object(provider, 'build_opener') as opener:
            opener.return_value.open.return_value = Response()
            response = self.client.post('/api/v1/system/digitalocean', json={'token': TOKEN})
        self.assertEqual(response.status_code, 200, response.text)
        report = self.client.get('/api/v1/system/logs/export').json()
        event = next(e for e in report['events'] if e['event'] == 'provider.http.completed')
        self.assertEqual(event['details']['http_status'], 200)
        self.assertEqual(event['details']['shape'], {'namespaces': 'NoneType'})
        self.assertEqual(event['details']['provider_request_id'], Response.headers['X-Request-Id'])
        self.assertNotIn(TOKEN, json.dumps(report))
        self.assertNotIn('unexpected', json.dumps(report))

    def test_namespace_auth_rejects_untrusted_destinations_and_redirects(self):
        for host in ('http://x.doserverless.co', 'https://doserverless.co.attacker.invalid',
                     'https://127.0.0.1', 'https://x.doserverless.co@attacker.invalid',
                     'https://x.doserverless.co:444', 'https://x.doserverless.co/path'):
            with patch.object(provider, 'request') as request:
                with self.assertRaises(provider.ProviderError):
                    provider.namespace_api({**NAMESPACE, 'api_host': host}, '/actions')
                self.assertFalse(request.called)
        with patch.object(provider, 'request', return_value={}) as request:
            provider.namespace_api(NAMESPACE, '/packages/test', 'PUT', {'publish': False})
            authorization = request.call_args.args[1]
            self.assertEqual(base64.b64decode(authorization.split()[1]).decode(), NAMESPACE['uuid'] + ':' + NAMESPACE['key'])
        self.assertIsNone(provider.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://attacker.invalid'))
        with patch.object(provider, 'build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError(provider.API, 302, 'TOKEN_SHOULD_NOT_APPEAR', {}, None)
            with self.assertRaisesRegex(provider.ProviderError, '^PROVIDER_HTTP_302$'):
                provider.request(provider.API, 'Bearer ' + TOKEN)

    def test_deployment_ack_does_not_buffer_the_provider_binary_echo_but_normal_reads_stay_bounded(self):
        class Response:
            status = 200
            headers = {'Content-Type': 'application/json'}
            def read(self, limit):
                raise AssertionError('A successful action upload must not buffer its large binary echo')
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with patch.object(provider, 'build_opener') as opener:
            opener.return_value.open.return_value = Response()
            self.assertEqual(provider.request(provider.API, 'Bearer ' + TOKEN, method='PUT', body={}, acknowledge=True), {'accepted': True})
        with patch.object(provider, 'request', return_value={}) as remote:
            provider.namespace_api(NAMESPACE, '/actions/caesar-demo/extract?overwrite=true', 'PUT', {})
            self.assertTrue(remote.call_args.kwargs['acknowledge'])
        class TooBig(Response):
            def read(self, limit): return b'X' * limit
        with patch.object(provider, 'build_opener') as opener:
            opener.return_value.open.return_value = TooBig()
            with self.assertRaisesRegex(provider.ProviderError, '^PROVIDER_RESPONSE_TOO_LARGE$'):
                provider.request(provider.API, 'Bearer ' + TOKEN)

    def test_namespace_creation_handles_null_list_and_detail_identity_is_checked(self):
        self.connect()
        project = self.upload(self.create())
        provider.queue(main, {'id': 'local-engineer', 'tenant': 'local', 'role': 'admin'}, project['id'], project['sheets'][0]['source_id'], 'syd1')
        provider.record(main.DATA, provider.current(main.DATA), 'namespace')
        with patch.object(provider, 'request', side_effect=[{'namespaces': None}, {'namespace': NAMESPACE}]):
            self.assertTrue(provider.advance(main))
        self.assertEqual(provider.current(main.DATA)['stage'], 'deploy')
        with patch.object(provider, 'request', return_value={'namespace': {**NAMESPACE, 'namespace': 'fn-' + '0' * 36}}):
            with self.assertRaisesRegex(provider.ProviderError, '^NAMESPACE_IDENTITY_MISMATCH$'):
                provider.namespace_details(TOKEN, NAMESPACE)

    def test_full_demo_pending_activation_to_website_excel_and_csv_without_project_mutation(self):
        self.connect()
        project = self.upload(self.create())
        before = json.dumps(project, sort_keys=True)
        source = project['sheets'][0]['source_id']
        body = {'project_id': project['id'], 'source_id': source, 'region': 'syd1'}
        response = self.client.post('/api/v1/system/digitalocean/demo', json=body)
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(self.client.post('/api/v1/system/digitalocean/demo', json=body).status_code, 409)
        self.assertEqual(self.client.delete('/api/v1/system/digitalocean').status_code, 409)
        home = provider.directory(main.DATA)
        job = provider.current(main.DATA)
        work = home / job['id']
        package = b'FAKE_TEST_DEPLOYMENT_PACKAGE'
        def build(output):
            output.mkdir()
            (output / 'extract.zip').write_bytes(package)
            write(output / 'build-report.json', {'zip_sha256': hashlib.sha256(package).hexdigest()})
        with patch('scripts.build_functions_demo.build', side_effect=build):
            self.assertTrue(provider.advance(main))
        label = 'caesar-demo-' + hashlib.sha256(str(main.DATA.resolve()).encode()).hexdigest()[:10]
        namespace = {**NAMESPACE, 'label': label, 'region': 'syd1'}
        summary = {**namespace, 'uuid': '', 'key': ''}
        with patch.object(provider, 'request', side_effect=[{'namespaces': [summary]}, {'namespace': namespace}]) as remote:
            self.assertTrue(provider.advance(main))
            self.assertEqual(remote.call_args.args[0], provider.API + '/' + namespace['namespace'])
        with patch.object(provider, 'namespace_api', return_value={}) as remote:
            self.assertTrue(provider.advance(main))
            action = remote.call_args.args[3]
            self.assertFalse(action['publish'])
            self.assertEqual(action['annotations'], [{'key': 'web-export', 'value': False}])
            self.assertNotIn(TOKEN, json.dumps(action))
        with patch.object(provider, 'namespace_api', return_value={'activationId': 'a' * 32}) as remote:
            self.assertTrue(provider.advance(main))
            self.assertEqual(set(remote.call_args.args[3]), {'pdf_base64', 'sha256', 'page'})
        job = provider.current(main.DATA)
        job['next_at'] = 0
        write(home / 'demo.json', job)
        with patch.object(provider, 'namespace_api', return_value=None):
            self.assertFalse(provider.advance(main))
        job = provider.current(main.DATA)
        job['next_at'] = 0
        write(home / 'demo.json', job)
        evidence = extract_page(work / 'source.pdf', 0, ocr=False)
        evidence['isolation'] = 'provider-function'
        result = {'format': 'caesar-function-result-1', 'ok': True, 'encoding': 'gzip+base64',
                  'evidence': base64.b64encode(gzip.compress(json.dumps(evidence).encode())).decode(),
                  'elapsed_ms': 13, 'parser_peak_rss_kib': 12345}
        with patch.object(provider, 'namespace_api', return_value={'response': {'result': {'body': result}}}):
            self.assertTrue(provider.advance(main))
        self.assertTrue(provider.advance(main))
        status = self.client.get('/api/v1/system/digitalocean').json()
        self.assertEqual(status['demo']['state'], 'done', status)
        self.assertTrue(status['demo']['report']['digitalocean_live_tested'])
        self.assertFalse(status['demo']['report']['project_modified'])
        self.assertNotIn(NAMESPACE['key'], json.dumps(status))
        self.assertNotIn(TOKEN, json.dumps(status))
        book_response = self.client.get(f"/api/v1/system/digitalocean/demo/{job['id']}/xlsx")
        self.assertEqual(book_response.status_code, 200, book_response.text[:200])
        workbook = load_workbook(io.BytesIO(book_response.content))
        self.assertIn('Components', workbook.sheetnames)
        self.assertIn('ENGINEERING REVIEW', workbook['Read me']['B7'].value)
        self.assertEqual(json.dumps(self.client.get(f"/api/v1/projects/{project['id']}").json(), sort_keys=True), before)
        self.assertEqual(self.client.get(f"/api/v1/system/digitalocean/demo/{job['id']}/csv").status_code, 200)
        self.assertEqual(self.client.get('/api/v1/system/digitalocean/demo/../../credentials.json/json').status_code, 404)

    def test_ambiguous_submission_is_not_repeated_and_provider_error_hides_secrets(self):
        self.connect()
        project = self.upload(self.create())
        provider.queue(main, {'id': 'local-engineer', 'tenant': 'local', 'role': 'admin'},
                       project['id'], project['sheets'][0]['source_id'], 'syd1')
        job = provider.current(main.DATA)
        provider.record(main.DATA, job, 'submitting')
        with patch.object(provider, 'namespace_api') as remote:
            self.assertTrue(provider.advance(main))
            self.assertFalse(remote.called)
        self.assertEqual(provider.public_job(main.DATA)['error'], 'SUBMISSION_INTERRUPTED_CHECK_PROVIDER')

    def test_source_and_tenant_ownership_checked_before_queue(self):
        self.connect()
        project = self.upload(self.create())
        with main.db() as conn:
            conn.execute('UPDATE projects SET tenant=? WHERE id=?', ('someone-else', project['id']))
        response = self.client.post('/api/v1/system/digitalocean/demo', json={
            'project_id': project['id'], 'source_id': project['sheets'][0]['source_id'], 'region': 'syd1'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(provider.current(main.DATA))
