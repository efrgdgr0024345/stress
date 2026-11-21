"""Installer lifecycle against a simulated Selector and a real local HTTP site.

These checks do not claim that this workspace is an actual CloudLinux server.
"""

from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from scripts import install_cpanel as setup


class FakeSelector:
    def __init__(self, home, public):
        self.home, self.public = home, public
        self.apps, self.calls = {}, []
        self.fail = None

    def call(self, action, *arguments):
        self.calls.append(action)
        if action == self.fail:
            raise setup.InstallError("simulated provider failure")
        if action == "get":
            username = arguments[1]
            return {"result": "success", "selector_enabled": True, "available_versions": {
                "3.12": {"users": {username: {"applications": self.apps.copy()}}}}}
        if action == "create":
            self.apps["caesar-system"] = {"domain": "easyai.com.au", "app_uri": "stress", "startup_file": "passenger_wsgi.py", "entry_point": "application"}
            (self.public / ".htaccess").write_text("PassengerAppRoot private-caesar-system\n")
            (self.home / "caesar-system/passenger_wsgi.py").write_text("# generated provider starter\n")
        return {"result": "success"}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.public = self.home / "public_html/stress"
        self.public.mkdir(parents=True)
        (self.public / "loader.php").write_text("original PHP loader")
        (self.public / ".htaccess").write_text("original routing")
        (self.public / "keep.txt").write_text("existing unrelated file")
        self.values = {"CAESAR_ADMIN_EMAIL": "pilot@example.invalid", "CAESAR_ADMIN_PASSWORD": "synthetic-test-password-987", "CAESAR_DATA_DIR": str(self.home / "caesar-data/caesar-system"), "CAESAR_LOCAL_DEMO": "0", "CAESAR_SECURE_COOKIE": "1"}
        self.settings = self.home / ".config/caesar/caesar-system.json"
        setup.private_write(self.settings, json.dumps(self.values))
        self.files = setup.unpack_bundle((Path(__file__).resolve().parents[2] / "downloads/caesar-cpanel.zip").read_bytes())
        self.selector = FakeSelector(self.home, self.public)
        test = self

        class Site(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, code, value, cookie=None):
                self.send_response(code)
                if cookie:
                    self.send_header("Set-Cookie", cookie)
                self.end_headers()
                self.wfile.write(value if isinstance(value, bytes) else json.dumps(value).encode())

            def do_GET(self):
                path = self.path.removeprefix("/stress/")
                if path == "api/v1/health":
                    self.send(200, {"mode": "authenticated"})
                elif path == "api/v1/projects":
                    self.send(200 if self.headers.get("Cookie") == "pilot=ok" else 401, [])
                elif (test.public / path).is_file():
                    self.send(200, (test.public / path).read_bytes())
                else:
                    self.send(404, {})

            def do_POST(self):
                if self.path == "/stress/api/v1/auth/login":
                    body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    success = body == {"email": test.values["CAESAR_ADMIN_EMAIL"], "password": test.values["CAESAR_ADMIN_PASSWORD"]}
                    self.send(200 if success else 401, {}, "pilot=ok; Path=/stress/")
                elif self.path == "/stress/api/v1/auth/logout":
                    self.send(200, {}, "pilot=; Max-Age=0; Path=/stress/")
                else:
                    self.send(404, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Site)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def installer(self):
        installer = setup.Installer(self.home, "easyai.com.au", "stress", selector=self.selector)
        installer.url = f"http://127.0.0.1:{self.server.server_port}/stress/"
        return installer

    def test_first_install_and_rerun_keep_credentials_data_and_backups(self):
        data = Path(self.values["CAESAR_DATA_DIR"])
        data.mkdir(parents=True)
        (data / "original-drawing.pdf").write_bytes(b"non-sensitive existing data")
        credentials = self.settings.read_bytes()
        first = self.installer()
        output = io.StringIO()
        with redirect_stdout(output):
            first.run(self.files)
            second = self.installer()
            second.run(self.files)
        self.assertIn("READY:", output.getvalue())
        self.assertNotIn(self.values["CAESAR_ADMIN_PASSWORD"], output.getvalue())
        self.assertEqual(self.selector.calls.count("create"), 1)
        self.assertEqual(self.selector.calls.count("restart"), 2)
        self.assertEqual(self.selector.calls.count("stop"), 1)
        self.assertEqual(self.settings.read_bytes(), credentials)
        self.assertEqual((first.backup / "public/loader.php").read_text(), "original PHP loader")
        self.assertEqual((first.backup / "public/.htaccess").read_text(), "original routing")
        self.assertEqual((first.backup / "provider-startup-template.py").read_text(), "# generated provider starter\n")
        self.assertEqual((data / "original-drawing.pdf").read_bytes(), b"non-sensitive existing data")
        self.assertEqual((second.backup / "private-data/original-drawing.pdf").read_bytes(), b"non-sensitive existing data")
        self.assertEqual((self.home / "caesar-system/passenger_wsgi.py").read_bytes(), self.files["passenger_wsgi.py"])
        self.assertEqual((self.public / "keep.txt").read_text(), "existing unrelated file")
        self.assertEqual({p.name for p in self.public.iterdir()}, {"keep.txt", "loader.php", ".htaccess", "LESSONS_LEARNED.md"})

    def test_conflicting_existing_app_is_not_changed(self):
        self.selector.apps["caesar-system"] = {"domain": "another.example", "app_uri": "different"}
        with self.assertRaisesRegex(setup.InstallError, "conflicts"):
            self.installer().run(self.files)
        self.assertEqual(self.selector.calls, ["get"])
        self.assertEqual((self.public / ".htaccess").read_text(), "original routing")
        self.assertFalse((self.home / "caesar-system").exists())

    def test_failed_dependency_install_can_be_resumed(self):
        self.selector.fail = "install-modules"
        with redirect_stdout(io.StringIO()):
            with self.assertRaises(setup.InstallError):
                self.installer().run(self.files)
            self.selector.fail = None
            self.installer().run(self.files)
        self.assertEqual(self.selector.calls.count("create"), 1)
        self.assertEqual((self.public / "loader.php").read_bytes(), self.files["loader.php"])

    def test_checksum_and_traversal_rejected(self):
        with self.assertRaisesRegex(setup.InstallError, "checksum"):
            setup.unpack_bundle(b"wrong download")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("caesar-system/../../outside.txt", "unsafe")
        content = output.getvalue()
        with self.assertRaisesRegex(setup.InstallError, "Unsafe"):
            setup.unpack_bundle(content, hashlib.sha256(content).hexdigest())

    def test_selector_error_is_private_even_when_cli_exits_zero(self):
        result = subprocess.CompletedProcess([], 0, '{"result":"error","env_vars":{"password":"private-value"}}', "")
        selector = setup.Selector("fake-selector", self.home / "private-logs")
        with patch.object(setup.subprocess, "run", return_value=result), redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(setup.InstallError) as failure:
                selector.call("get", "--user", "test")
        self.assertNotIn("private-value", output.getvalue() + str(failure.exception))
        log = next((self.home / "private-logs").iterdir())
        self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_wrong_public_mapping_stops_before_routing_changes(self):
        installer = self.installer()
        installer.url += "wrong/"
        with self.assertRaises(setup.InstallError), redirect_stdout(io.StringIO()):
            installer.run(self.files)
        self.assertEqual(self.selector.calls, ["get"])
        self.assertEqual((self.public / ".htaccess").read_text(), "original routing")
        self.assertFalse(list(self.public.glob("caesar-check-*")))
