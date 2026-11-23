"""Gate mechanics use disposable bytes, never substitute golden engineering data."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts.audit_1010_golden import audit,ROLES,safe_file,REVIEWED_SHA


class GoldenAssetGateTests(unittest.TestCase):
    def test_missing_inventory_is_explicitly_blocked_with_unknown_expected_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'golden-manifest.json').write_text(json.dumps({'format':'caesar-1010-golden-manifest-1',
                'assets':{role:{'path':role,'expected_sha256':None,'trusted_hash_source':None} for role in ROLES}}))
            result=audit(root)
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual({r['role'] for r in result['assets']},set(ROLES))
        self.assertTrue(all(r['expected_sha256'] is None for r in result['assets']))
        self.assertFalse(result['legacy_tests_restored']);self.assertFalse(result['engineering_verified'])

    def test_renaming_reviewed_pdf_does_not_make_it_the_original(self):
        source=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'1010_original.pdf').write_bytes(source.read_bytes())
            assets={role:{'path':role,'expected_sha256':None,'trusted_hash_source':None} for role in ROLES}
            assets['original_pdf']={'path':'1010_original.pdf','expected_sha256':REVIEWED_SHA,'trusted_hash_source':'Gate-mechanics negative test'}
            (root/'golden-manifest.json').write_text(json.dumps({'format':'caesar-1010-golden-manifest-1','assets':assets}))
            row=next(r for r in audit(root)['assets'] if r['role']=='original_pdf')
            self.assertFalse(row['ready']);self.assertIn('REVIEWED_PDF_IS_NOT_THE_ORIGINAL_FIXTURE',row['issues'])

    def test_hash_mismatch_cannot_be_accepted_and_no_file_is_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);payload=b'GATE MECHANICS ONLY, NOT A DRAWING'
            assets={}
            for role in ROLES:
                (root/role).write_bytes(payload)
                assets[role]={'path':role,'expected_sha256':hashlib.sha256(payload).hexdigest(),'trusted_hash_source':'Synthetic gate-mechanics test only'}
            path=root/'golden-manifest.json';path.write_text(json.dumps({'format':'caesar-1010-golden-manifest-1','assets':assets}))
            self.assertEqual(audit(root)['status'],'READY') # Availability/pins only; not any engineering acceptance.
            before=(root/'original_pdf').read_bytes();assets['original_pdf']['expected_sha256']='0'*64
            path.write_text(json.dumps({'format':'caesar-1010-golden-manifest-1','assets':assets}))
            result=audit(root);self.assertEqual(result['status'],'BLOCKED')
            self.assertIn('SHA256_MISMATCH',next(r for r in result['assets'] if r['role']=='original_pdf')['issues'])
            self.assertEqual((root/'original_pdf').read_bytes(),before)

    def test_deleted_required_role_and_path_escapes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('../outside','/tmp/outside','x\\y',None):
                with self.subTest(name=name),self.assertRaises(ValueError):safe_file(root,name)
            target=root/'link';target.symlink_to('/tmp')
            with self.assertRaises(ValueError):safe_file(root,'link/anything')
            (root/'golden-manifest.json').write_text(json.dumps({'format':'caesar-1010-golden-manifest-1','assets':{}}))
            with self.assertRaises(ValueError):audit(root)
