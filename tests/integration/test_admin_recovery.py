"""Exercise recovery against the real API's password/session implementation."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from services.api import main
from scripts import reset_admin as recovery


class AdminRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.email = "owner@example.invalid"
        self.password = "original-test-password-987"
        self.new_password = "replacement-test-password-654"
        self.settings = self.home / ".config/caesar/caesar-system.json"
        self.settings.parent.mkdir(parents=True, mode=0o700)
        self.settings.write_text(json.dumps({"CAESAR_DATA_DIR": str(self.home / "data"), "CAESAR_ADMIN_EMAIL": self.email, "CAESAR_ADMIN_PASSWORD": self.password, "CAESAR_LOCAL_DEMO": "0", "CAESAR_SECURE_COOKIE": "1"}))
        self.settings.chmod(0o600)
        self.original_data, self.original_mode = main.DATA, main.LOCAL_DEMO
        main.DATA, main.LOCAL_DEMO = self.home / "data", False
        self.environment = patch.dict(os.environ, {"CAESAR_ADMIN_EMAIL": self.email, "CAESAR_ADMIN_PASSWORD": self.password, "CAESAR_SECURE_COOKIE": "1"})
        self.environment.start()
        self.context = TestClient(main.app, base_url="https://testserver")
        self.client = self.context.__enter__()
        response = self.client.post("/api/v1/auth/login", json={"email": self.email, "password": self.password})
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/v1/projects", json={"title": "Preserved recovery fixture", "line_id": "RECOVERY-01"})
        self.assertEqual(response.status_code, 201)
        self.project = response.json()
        self.original_configuration = self.settings.read_bytes()

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.environment.stop()
        main.DATA, main.LOCAL_DEMO = self.original_data, self.original_mode
        self.temp.cleanup()

    def test_recovery_updates_login_config_and_revokes_old_session(self):
        result = recovery.reset_credentials(self.home, "recovered@example.invalid", self.new_password)
        self.assertEqual(self.client.get("/api/v1/projects").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/login", json={"email": self.email, "password": self.password}).status_code, 401)
        response = self.client.post("/api/v1/auth/login", json={"email": "recovered@example.invalid", "password": self.new_password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "admin")
        self.assertEqual(self.client.get(f"/api/v1/projects/{self.project['id']}").json(), self.project)
        values = json.loads(self.settings.read_text())
        self.assertEqual(values["CAESAR_ADMIN_PASSWORD"], self.new_password)
        self.assertEqual(self.settings.stat().st_mode & 0o777, 0o600)
        backup = Path(result["backup"])
        self.assertEqual((backup / "configuration.json").read_bytes(), self.original_configuration)
        self.assertEqual((backup / "administrator.json").stat().st_mode & 0o777, 0o600)
        with main.db() as conn:
            row = conn.execute("SELECT * FROM users WHERE id='admin'").fetchone()
            self.assertEqual((row["role"], row["tenant"]), ("admin", "default"))
            self.assertNotEqual(row["password"], self.new_password)
            event = conn.execute("SELECT * FROM audit WHERE action='Administrator credentials recovered'").fetchone()
            self.assertNotIn(self.new_password, event["detail"])

    def test_failed_configuration_write_rolls_back_credentials_and_sessions(self):
        with patch.object(recovery, "replace_configuration", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                recovery.reset_credentials(self.home, self.email, self.new_password)
        self.assertEqual(self.settings.read_bytes(), self.original_configuration)
        self.assertEqual(self.client.get("/api/v1/projects").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/login", json={"email": self.email, "password": self.password}).status_code, 200)

    def test_duplicate_email_preserves_existing_accounts(self):
        with main.db() as conn:
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", ("another", "Another user", "taken@example.invalid", "", "viewer", "another-tenant"))
        with self.assertRaisesRegex(recovery.RecoveryError, "another existing account"):
            recovery.reset_credentials(self.home, "taken@example.invalid", self.new_password)
        self.assertEqual(self.settings.read_bytes(), self.original_configuration)
        self.assertEqual(self.client.get("/api/v1/projects").status_code, 200)
        with main.db() as conn:
            self.assertEqual(conn.execute("SELECT role FROM users WHERE id='another'").fetchone()[0], "viewer")

    def test_readable_configuration_is_refused(self):
        self.settings.chmod(0o644)
        with self.assertRaisesRegex(recovery.RecoveryError, "permissions 600"):
            recovery.reset_credentials(self.home, self.email, self.new_password)
        self.assertEqual(self.client.get("/api/v1/projects").status_code, 200)

    def test_short_password_is_refused_without_changing_login(self):
        with self.assertRaisesRegex(recovery.RecoveryError, "12 and 1024"):
            recovery.reset_credentials(self.home, self.email, "short")
        self.assertEqual(self.settings.read_bytes(), self.original_configuration)
        self.assertEqual(self.client.get("/api/v1/projects").status_code, 200)

    def test_interactive_recovery_does_not_print_password(self):
        with patch.object(recovery.Path, "home", return_value=self.home), patch.object(recovery.sys.stdin, "isatty", return_value=True), patch("builtins.input", return_value=""), patch.object(recovery, "getpass", return_value=self.new_password), redirect_stdout(io.StringIO()) as output:
            recovery.main()
        self.assertIn("Administrator login updated", output.getvalue())
        self.assertIn(self.email, output.getvalue())
        self.assertNotIn(self.password, output.getvalue())
        self.assertNotIn(self.new_password, output.getvalue())
