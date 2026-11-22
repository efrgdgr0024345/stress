import hashlib
import fcntl
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from services.api import updates as u
from tests.integration import test_api as fixtures

ROOT=Path(__file__).resolve().parents[2]

class UpdateApiTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    def test_maintenance_public_checks_pass_but_project_actions_stay_blocked(self):
        from services.api import main
        from fastapi.testclient import TestClient
        from urllib.parse import urlsplit
        u.write(main.DATA/'updates/maintenance.json',{'active':True})
        for mount in ('','/stress'):
            client=TestClient(main.app,root_path=mount,base_url='https://testserver')
            index=client.get(mount+'/')
            self.assertEqual(index.status_code,200,index.text[:200])
            import re
            asset=re.search(r'assets/[A-Za-z0-9_.-]+\.js',index.text).group(0)
            self.assertEqual(client.get(mount+'/'+asset).status_code,200)
            self.assertEqual(client.post(mount+'/',json={}).status_code,503)
            self.assertEqual(client.get(mount+'/api/v1/projects').status_code,503)
            self.assertEqual(client.post(mount+'/api/v1/projects',json={}).status_code,503)
            def fetch(url,limit=1000000):
                response=client.get(urlsplit(url).path)
                response.raise_for_status()
                return response.content
            with patch.object(main,'LOCAL_DEMO',False),patch.object(u,'fetch',side_effect=fetch):
                self.assertTrue(u.healthy('https://testserver'+mount,main.BUILD_ID,ROOT))
            client.close()
    def test_updates_require_admin(self):
        from services.api import main
        self.assertEqual(self.client.get('/api/v1/system/updates').status_code,200)
        with main.db() as connection:connection.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertEqual(self.client.get('/api/v1/system/updates').status_code,403)
        self.assertEqual(self.client.post('/api/v1/system/updates/install').status_code,403)
    def test_queue_requires_runner_and_is_serialized(self):
        from services.api import main
        directory=main.DATA/'updates'
        self.assertEqual(self.client.post('/api/v1/system/updates/install').status_code,409)
        u.write(directory/'config.json',{'enabled':True})
        u.write(directory/'heartbeat.json',{'at':time.time()})
        u.write(directory/'available.json',{'commit':'a'*40})
        self.assertEqual(self.client.post('/api/v1/system/updates/install').status_code,200)
        self.assertEqual(self.client.post('/api/v1/system/updates/install').status_code,409)
    def test_tenant_admin_cannot_deploy_host_code(self):
        from services.api import main
        with main.db() as connection:
            connection.execute("INSERT INTO users VALUES (?,?,?,?,?,?)",('tenant-admin','Team admin','team@example.invalid','','admin','another'))
            connection.execute("UPDATE sessions SET user_id='tenant-admin'")
        previous=main.LOCAL_DEMO
        try:
            main.LOCAL_DEMO=False
            self.assertEqual(self.client.get('/api/v1/system/updates').status_code,403)
            self.assertEqual(self.client.post('/api/v1/system/updates/install').status_code,403)
        finally:main.LOCAL_DEMO=previous

class ReleaseTests(unittest.TestCase):
    def test_security_downgrade_cannot_bypass_mfa_disabled_accounts_or_reviews(self):
        with tempfile.TemporaryDirectory() as temporary:
            root,public,data,directory,config,release=self.fixture(Path(temporary))
            self.assertEqual(u.required_security_contract(data),0)
            u.security_compatible(data,root)
            u.write(data/'security/mfa/fixture.json',{'enabled':True,'secret':'DISPOSABLE'})
            with self.assertRaisesRegex(ValueError,'predates'):u.security_compatible(data,root)
            u.write(root/'RELEASE.json',{'version':'compatible','security_contract':1})
            u.security_compatible(data,root)
            (data/'security/mfa/fixture.json').unlink()
            with sqlite3.connect(data/'workspace.sqlite3') as conn:
                conn.execute('CREATE TABLE account_state (user_id TEXT,enabled INTEGER)')
                conn.execute("INSERT INTO account_state VALUES ('disabled-fixture',0)")
            self.assertEqual(u.required_security_contract(data),1)
            with sqlite3.connect(data/'workspace.sqlite3') as conn:
                conn.execute('DELETE FROM account_state')
                conn.execute('CREATE TABLE review_signoffs (id TEXT)')
                conn.execute("INSERT INTO review_signoffs VALUES ('signed-fixture')")
            self.assertEqual(u.required_security_contract(data),1)

    def test_update_waits_for_inflight_cloud_pages_until_the_result_is_delivered(self):
        with tempfile.TemporaryDirectory() as temporary:
            root,public,data,directory,config,release=self.fixture(Path(temporary))
            with sqlite3.connect(data/'workspace.sqlite3') as conn:
                conn.execute('CREATE TABLE remote_pages (state TEXT,deadline REAL)')
                conn.execute("INSERT INTO remote_pages VALUES ('SUBMITTED',?)",(time.time()+240,))
            with u.pipeline_guard(directory) as ready:self.assertFalse(ready)
            with sqlite3.connect(data/'workspace.sqlite3') as conn:
                conn.execute("UPDATE remote_pages SET state='RESULT_READY'")
            with u.pipeline_guard(directory) as ready:self.assertTrue(ready)

    def test_update_waits_without_swapping_code_while_drawing_worker_is_busy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root,public,data,directory,config,release=self.fixture(Path(temporary))
            worker=data/'pipeline';worker.mkdir()
            u.write(directory/'state.json',{'status':'queued','action':'install'})
            with (worker/'runner.lock').open('a') as running:
                fcntl.flock(running,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch.object(u,'activate') as activate:u.run(directory)
                activate.assert_not_called()
            self.assertEqual(u.read(directory/'state.json')['status'],'queued')
            self.assertEqual((root/'marker').read_text(),'old code')
    def test_hash_and_traversal_rejected(self):
        import io,zipfile
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):u.unpack(b'bad',{'package_sha256':'0'*64},Path(temporary))
            b=io.BytesIO()
            with zipfile.ZipFile(b,'w') as z:z.writestr('caesar-system/../../escape','bad')
            data=b.getvalue()
            with self.assertRaises(ValueError):u.unpack(data,{'package_sha256':hashlib.sha256(data).hexdigest()},Path(temporary))
    def fixture(self, home):
        root=home/'caesar-system';root.mkdir()
        for name in ('requirements.txt','requirements-cpanel.txt'):(root/name).write_bytes((ROOT/name).read_bytes())
        (root/'marker').write_text('old code')
        (root/'RELEASE.json').write_text('{"version":"old"}')
        public=home/'public';public.mkdir();(public/'index.html').write_text('old frontend')
        data=home/'data';data.mkdir()
        with sqlite3.connect(data/'workspace.sqlite3') as db:
            db.execute('PRAGMA user_version=2');db.execute('CREATE TABLE projects (value TEXT)');db.execute("INSERT INTO projects VALUES ('retained')")
        directory=data/'updates';directory.mkdir()
        config={'app_root':str(root),'public_dir':str(public),'data_dir':str(data),'url':'https://example.invalid/stress/'}
        u.write(directory/'config.json',config)
        release=json.loads((ROOT/'updates/stable.json').read_text());release['commit']='a'*40
        return root,public,data,directory,config,release
    def test_failed_health_restores_code_and_frontend(self):
        with tempfile.TemporaryDirectory() as temporary:
            root,public,data,directory,config,release=self.fixture(Path(temporary))
            with patch.object(u,'fetch',return_value=(ROOT/'downloads/caesar-cpanel.zip').read_bytes()),patch.object(u.subprocess,'run',return_value=subprocess.CompletedProcess([],0)),patch.object(u,'restart'),patch.object(u,'healthy',return_value=False):
                with self.assertRaisesRegex(ValueError,'health'):u.activate(directory,config,release)
            self.assertEqual((root/'marker').read_text(),'old code')
            self.assertEqual((public/'index.html').read_text(),'old frontend')
            self.assertFalse((directory/'maintenance.json').exists())
    def test_success_then_manual_rollback_preserves_new_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root,public,data,directory,config,release=self.fixture(Path(temporary))
            with patch.object(u,'fetch',return_value=(ROOT/'downloads/caesar-cpanel.zip').read_bytes()),patch.object(u.subprocess,'run',return_value=subprocess.CompletedProcess([],0)),patch.object(u,'restart'),patch.object(u,'healthy',return_value=True):
                u.activate(directory,config,release)
                with sqlite3.connect(data/'workspace.sqlite3') as db:db.execute("INSERT INTO projects VALUES ('new edit')")
                u.rollback(directory,config)
            self.assertEqual((root/'marker').read_text(),'old code')
            with sqlite3.connect(data/'workspace.sqlite3') as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM projects').fetchone()[0],2)
    def test_interrupted_swap_recovers_on_next_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root,public,data,directory,config,release=self.fixture(Path(temporary))
            backup=directory/'backups/test';backup.mkdir(parents=True)
            root.rename(backup/'code')
            u.write(directory/'journal.json',{'backup':str(backup),'root':str(root),'public':str(public)})
            u.write(directory/'maintenance.json',{'active':True})
            with patch.object(u,'restart'):u.run(directory)
            self.assertEqual((root/'marker').read_text(),'old code')
            self.assertFalse((directory/'maintenance.json').exists())
            self.assertEqual(u.read(directory/'state.json')['status'],'failed')
