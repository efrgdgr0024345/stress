"""Authorized clean workspace, private recovery and retained system state."""
from pathlib import Path
import json
import unittest
from unittest.mock import patch
from services.api import main,workspace_reset
from services.api.updates import write
from tests.integration import test_api as fixtures


class WorkspaceResetTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload
    pdf=fixtures.ApiTests.pdf
    path='/api/v1/system/workspace-reset'

    def reset(self):
        value=self.client.get(self.path).json()
        return self.client.post(self.path,json={'plan_sha256':value['plan_sha256'],'confirmation':'CLEAR PROJECT DATA'})

    def test_clear_projects_keeps_login_reference_library_provider_and_usage(self):
        p=self.upload(self.create());source=main.DATA/'sources'/f"{p['sheets'][0]['source_id']}.pdf";original=source.read_bytes()
        reference=main.DATA/'catalogs/reference.xlsx';reference.write_bytes(b'private fixture reference')
        credentials=main.DATA/'providers/digitalocean/credentials.json';write(credentials,{'token':'private-disposable-fixture'})
        demo_id=main.uid();demo=main.DATA/'providers/digitalocean'/demo_id;demo.mkdir()
        (demo/'results.xlsx').write_bytes(b'disposable demonstration output')
        write(demo.parent/'demo.json',{'id':demo_id,'project_id':p['id'],'state':'done'})
        write(demo.parent/'processing/setup.json',{'state':'ready'})
        with main.db() as conn:
            conn.execute('INSERT INTO catalogs VALUES (?,?,?,?,?,?)',('reference','local','reference.xlsx','a'*64,main.now(),'{}'))
            conn.execute("INSERT INTO remote_usage VALUES ('month:fixture',17)")
            conn.execute("INSERT INTO users VALUES ('test-user','Software QA engineer fixture','software-review-engineer-fixture@example.invalid','fixture-hash','engineer','local')")
        response=self.reset();self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get('/api/v1/projects').json(),[])
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code,200)
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}").status_code,404)
        self.assertFalse(source.exists());self.assertTrue(reference.exists())
        self.assertEqual(json.loads(credentials.read_text())['token'],'private-disposable-fixture')
        self.assertFalse(demo.exists());self.assertFalse((demo.parent/'demo.json').exists())
        self.assertEqual(json.loads((demo.parent/'processing/setup.json').read_text())['state'],'ready')
        backup=main.DATA/'reset-backups'/response.json()['backup_id']
        self.assertEqual((backup/'files'/source.relative_to(main.DATA)).read_bytes(),original)
        self.assertEqual((backup/'database.sqlite3').stat().st_mode&0o777,0o600)
        self.assertTrue(json.loads((backup/'complete.json').read_text())['completed'])
        with main.db() as conn:
            self.assertIsNotNone(conn.execute("SELECT id FROM users WHERE id='local-engineer'").fetchone())
            self.assertIsNone(conn.execute("SELECT id FROM users WHERE id='test-user'").fetchone())
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM catalogs').fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT count FROM remote_usage WHERE bucket='month:fixture'").fetchone()[0],17)

    def test_changed_preview_and_pending_jobs_cannot_be_cleared(self):
        preview=self.client.get(self.path).json();p=self.upload(self.create())
        r=self.client.post(self.path,json={'plan_sha256':preview['plan_sha256'],'confirmation':'CLEAR PROJECT DATA'})
        self.assertEqual(r.status_code,409)
        with main.db() as conn:conn.execute('INSERT INTO pipeline_runs(id,project_id,source_id,state,progress) VALUES (?,?,?,?,?)',(main.uid(),p['id'],p['sheets'][0]['source_id'],'QUEUED','{}'))
        self.assertEqual(self.reset().status_code,409)
        self.assertFalse((main.DATA/'updates/maintenance.json').exists())
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}").status_code,200)

    def test_file_move_failure_rolls_back_database_and_all_prior_moves(self):
        p=self.upload(self.create());files={f:f.read_bytes() for f in (main.DATA/'sources').glob('*.pdf')}
        original=workspace_reset.os.replace;calls=0
        def move(a,b):
            nonlocal calls
            # Leave metadata writes alone; fail the second source file move.
            if str(a).endswith('.pdf') and '/reset-backups/' not in str(a):
                calls+=1
                if calls==2:raise OSError('Simulated storage failure')
            return original(a,b)
        with patch.object(workspace_reset.os,'replace',side_effect=move):
            failed=self.reset();self.assertEqual(failed.status_code,500,failed.text)
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}").status_code,200)
        self.assertTrue(all(f.read_bytes()==content for f,content in files.items()))
        self.assertFalse((main.DATA/'updates/maintenance.json').exists())

    def test_only_host_owner_and_current_tenant_data_are_in_scope(self):
        p=self.create()
        with main.db() as conn:conn.execute("UPDATE projects SET tenant='other' WHERE id=?",(p['id'],))
        response=self.reset();self.assertEqual(response.status_code,200,response.text)
        with main.db() as conn:
            self.assertIsNotNone(conn.execute('SELECT 1 FROM projects WHERE id=?',(p['id'],)).fetchone())
            conn.execute("UPDATE users SET role='reviewer' WHERE id='local-engineer'")
        self.assertEqual(self.client.get(self.path).status_code,403)
