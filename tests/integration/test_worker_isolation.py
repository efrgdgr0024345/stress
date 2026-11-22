"""Exercise the real supervisor's container boundary when Docker is available."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import fitz
from services.api.pipeline_executor import execute


def available():
    try:
        return bool(shutil.which('docker')) and subprocess.run(['docker','image','inspect',os.environ.get('CAESAR_PIPELINE_IMAGE','caesar-worker:local')],capture_output=True,timeout=10).returncode==0
    except (OSError,subprocess.TimeoutExpired):return False


@unittest.skipUnless(available(),'Build caesar-worker:local to qualify container isolation.')
class WorkerIsolationTests(unittest.TestCase):
    def test_supervised_worker_has_no_private_files_secrets_network_or_root_writes(self):
        with tempfile.TemporaryDirectory(prefix='caesar-private-test-') as tmp:
            path=Path(tmp)/'input.pdf';secret=Path(tmp)/'private-credential';secret.write_text('private-isolation-sentinel')
            doc=fitz.open();doc.new_page();doc.save(path);doc.close()
            original=subprocess.Popen
            def probe(command,**kwargs):
                if command[:2]==['docker','run']:
                    image=command.index(os.environ.get('CAESAR_PIPELINE_IMAGE','caesar-worker:local'))
                    code='''import json,os,pathlib,socket
assert 'CAESAR_ADMIN_PASSWORD' not in os.environ
assert not pathlib.Path(PRIVATE).exists()
try:
    pathlib.Path('/isolation-write-probe').write_text('forbidden')
except OSError: pass
else: raise AssertionError('container root was writable')
sock=socket.socket();sock.settimeout(2)
try:
    sock.connect(('1.1.1.1',443))
except OSError: pass
else: raise AssertionError('external network was reachable')
finally: sock.close()
pathlib.Path('/job/result.json').write_text(json.dumps({'boundary_checked':True}))
'''.replace('PRIVATE',repr(str(secret)))
                    command=command[:image]+['--entrypoint','python',command[image],'-c',code]
                return original(command,**kwargs)
            with patch.dict(os.environ,{'CAESAR_ADMIN_PASSWORD':'private-isolation-sentinel'}),patch('services.api.pipeline_executor.subprocess.Popen',side_effect=probe):result=execute(path,'register')
            self.assertTrue(result['boundary_checked']);self.assertEqual(result['isolation'],'container-no-network')

    def test_active_pdf_is_rejected_inside_the_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'active.pdf';doc=fitz.open();doc.new_page();action=doc.get_new_xref()
            doc.update_object(action,'<< /S /JavaScript /JS (app.alert(1)) >>');doc.xref_set_key(doc.pdf_catalog(),'OpenAction',f'{action} 0 R');doc.save(path);doc.close()
            with self.assertRaisesRegex(ValueError,'DOCUMENT_PROCESSING_FAILED'):execute(path,'register')
