import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('function_demo',ROOT/'serverless/digitalocean/function/__main__.py')
handler=importlib.util.module_from_spec(spec);spec.loader.exec_module(handler)


class FunctionDemoTests(unittest.TestCase):
    def event(self):
        pdf=b'%PDF-1.7 software-only validation'
        return {'pdf_base64':base64.b64encode(pdf).decode(),'sha256':hashlib.sha256(pdf).hexdigest(),'page':0}

    def test_invalid_hash_is_rejected_before_parsing(self):
        event=self.event();event['sha256']='0'*64
        with patch.object(handler.subprocess,'run') as run:
            self.assertEqual(handler.main(event)['body']['error'],'SOURCE_HASH_MISMATCH');run.assert_not_called()

    def test_arbitrary_urls_commands_and_invalid_page_types_are_not_accepted(self):
        for key in ('url','command','output_path'):
            self.assertEqual(handler.main({**self.event(),key:'untrusted'})['body']['error'],'INVALID_INPUT')
        self.assertEqual(handler.main({**self.event(),'page':True})['body']['error'],'INVALID_INPUT')

    def test_oversized_input_and_malformed_base64_are_rejected(self):
        self.assertEqual(handler.main({**self.event(),'pdf_base64':'A'*1_000_000})['body']['error'],'INVALID_INPUT')
        self.assertEqual(handler.main({**self.event(),'pdf_base64':'!!!'})['body']['error'],'INVALID_BASE64')

    def test_parent_secrets_are_not_forwarded_and_evidence_is_compressed(self):
        event=self.event();captured={}
        def worker(args,**kwargs):
            captured.update(kwargs['env'])
            value={'evidence':{'source_sha256':event['sha256'],'page_index':0,'words':[]},'parser_peak_rss_kib':12345}
            (Path(kwargs['cwd'])/'result.json').write_text(json.dumps(value))
            return subprocess.CompletedProcess(args,0)
        with patch.dict(os.environ,{'DIGITALOCEAN_ACCESS_TOKEN':'NEVER_FORWARD_THIS'}),patch.object(handler.subprocess,'run',side_effect=worker):result=handler.main(event)['body']
        self.assertNotIn('DIGITALOCEAN_ACCESS_TOKEN',captured);self.assertTrue(result['ok']);self.assertEqual(result['encoding'],'gzip+base64')
        self.assertNotIn('NEVER_FORWARD_THIS',json.dumps(result))

    def test_deadlines_and_failed_children_do_not_publish_partial_results(self):
        class Context:
            def get_remaining_time_in_millis(self):return 100
        self.assertEqual(handler.main(self.event(),Context())['body']['error'],'DEADLINE_EXCEEDED')
        with patch.object(handler.subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',1)):
            self.assertEqual(handler.main(self.event())['body']['error'],'PROCESSING_TIMEOUT')

    def test_symbolic_worker_output_is_rejected(self):
        def worker(args,**kwargs):
            directory=Path(kwargs['cwd']);(directory/'elsewhere').write_text('{}');(directory/'result.json').symlink_to(directory/'elsewhere')
            return subprocess.CompletedProcess(args,0)
        with patch.object(handler.subprocess,'run',side_effect=worker):self.assertEqual(handler.main(self.event())['body']['error'],'PROCESSING_FAILED')

    def test_deployment_without_credentials_makes_no_provider_requests(self):
        from scripts import deploy_functions_demo as deployment
        with patch.dict(os.environ,{},clear=True),patch.object(deployment,'api') as api:
            with self.assertRaisesRegex(RuntimeError,'no provider requests'):deployment.deploy(Path('/missing'),'syd1',Path('/missing/report'))
            api.assert_not_called()

    def test_provider_result_wrappers_are_unwrapped_without_exposing_context(self):
        from scripts.deploy_functions_demo import find_result
        result={'format':'caesar-function-result-1','ok':True}
        self.assertEqual(find_result({'response':{'result':{'body':result}}}),result)
        self.assertIsNone(find_result({'api_key':'SHOULD_NOT_BE_REPORTED'}))

    def remote(self):
        identity='11111111-1111-4111-8111-111111111111'
        event=self.event()
        root='https://easyai.com.au/stress/api/v1/worker/pages/'+identity
        return {'source_url':root+'/source','result_url':root+'/result','lease':'s'*43,
                'request_id':identity,'sha256':event['sha256'],'page':0}

    def test_remote_transport_rejects_foreign_urls_redirects_and_missing_activation_before_fetching(self):
        event=self.remote()
        with patch.object(handler,'transfer') as transfer:
            for key,value in [('source_url','https://attacker.invalid/source'),('result_url','http://127.0.0.1/result'),('lease','short')]:
                self.assertEqual(handler.main({**event,key:value})['body']['error'],'INVALID_TRANSFER_INPUT')
            with patch.dict(os.environ,{},clear=True):
                self.assertEqual(handler.main(event)['body']['error'],'ACTIVATION_CONTEXT_UNAVAILABLE')
            transfer.assert_not_called()
        self.assertIsNone(handler.NoRedirect().redirect_request(None,None,302,'',{},'https://attacker.invalid'))

    def test_remote_large_evidence_uses_private_callback_and_never_passes_lease_to_parser(self):
        event=self.remote();seen={};uploads=[]
        pdf=base64.b64decode(self.event()['pdf_base64'])
        def worker(args,**kwargs):
            seen.update(kwargs['env'])
            # Large evidence must use the transfer path rather than the 1 MB
            # invocation-result frame. The receiving API validates its schema.
            words=[{'text':base64.b64encode(os.urandom(225)).decode(),'bbox':[1,2,3,4],
                    'confidence':.9,'method':'ocr','evidence_id':'11111111-1111-4111-8111-111111111111'} for _ in range(5000)]
            value={'evidence':{'source_sha256':event['sha256'],'page_index':0,'words':words},'parser_peak_rss_kib':123456}
            (Path(kwargs['cwd'])/'result.json').write_text(json.dumps(value))
            return subprocess.CompletedProcess(args,0)
        def transfer(got,activation,body=None):
            self.assertEqual(got,event);self.assertEqual(activation,'a'*32)
            if body is None:return pdf
            uploads.append(body)
        with patch.dict(os.environ,{'__OW_ACTIVATION_ID':'a'*32,'DIGITALOCEAN_ACCESS_TOKEN':'PRIVATE_ACCOUNT_SENTINEL'}),patch.object(handler,'transfer',side_effect=transfer),patch.object(handler.subprocess,'run',side_effect=worker):
            result=handler.main(event)['body']
        self.assertTrue(result['ok']);self.assertEqual(result['delivery'],'callback')
        self.assertGreater(len(uploads[0]),handler.MAX_FRAME)
        self.assertNotIn(event['lease'],json.dumps(seen)+json.dumps(result))
        self.assertNotIn('PRIVATE_ACCOUNT_SENTINEL',json.dumps(seen)+json.dumps(result))
        self.assertEqual(len(json.loads(__import__('gzip').decompress(uploads[0]))['evidence']['words']),5000)
