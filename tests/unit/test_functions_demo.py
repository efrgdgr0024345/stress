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
