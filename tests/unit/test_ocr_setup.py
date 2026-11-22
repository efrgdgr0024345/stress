import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import types
import sys
import os
import fitz

from services.api import ocr_setup as ocr


class OcrSetupTests(unittest.TestCase):
    def test_portable_tsv_rows_keep_confidence_without_a_cli_header(self):
        from packages.automation.extract import extract_page
        class Engine:
            def __init__(self,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def SetImageFile(self,path):assert Path(path).is_file()
            def GetTSVText(self,page):return '5\t1\t1\t1\t1\t1\t20\t40\t50\t10\t91\tEVIDENCE\n'
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.pdf';doc=fitz.open();doc.new_page(width=500,height=400);doc.save(source);doc.close()
            with patch('packages.automation.extract.shutil.which',return_value=None),patch.dict(sys.modules,{'tesserocr':types.SimpleNamespace(PyTessBaseAPI=Engine)}),patch.dict(os.environ,{'CAESAR_OCR_HOME':tmp}):value=extract_page(source,0)
            self.assertTrue(value['ocr_used']);self.assertEqual(value['words'][0]['text'],'EVIDENCE');self.assertEqual(value['words'][0]['confidence'],.91)
            self.assertEqual(value['words'][0]['method'],'ocr')
    def test_corrupt_download_cannot_be_loaded(self):
        class Response(io.BytesIO):pass
        with patch.object(ocr,'urlopen',return_value=Response(b'corrupt')):
            with self.assertRaisesRegex(ValueError,'CHECKSUM'):ocr.download('https://example.invalid','0'*64)

    def test_archive_escape_and_unexpected_packages_are_rejected(self):
        for name in ('../outside','/absolute','unrelated/startup.pth','tesserocr/../../outside'):
            content=io.BytesIO()
            with zipfile.ZipFile(content,'w') as archive:archive.writestr(name,b'bad')
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(ValueError,'PATH_REJECTED'):ocr.unpack(content.getvalue(),Path(tmp))

    def test_failed_setup_retains_no_partial_engine_and_does_not_retry_forever(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);ocr.queue(data)
            with patch.object(ocr,'download',side_effect=ValueError('OCR_DOWNLOAD_CHECKSUM_FAILED')):self.assertTrue(ocr.run_pending(data))
            self.assertEqual(ocr.status(data)['state'],'failed');self.assertFalse((data/'pipeline/ocr').exists())
            self.assertFalse(ocr.run_pending(data));self.assertEqual(ocr.queue(data)['state'],'queued')
