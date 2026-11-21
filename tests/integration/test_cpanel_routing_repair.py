"""File preservation and rollback tests with simulated web-server responses."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from scripts import repair_cpanel_routing as routing


class RoutingRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.public = self.home / "easyai.com.au/stress"
        self.public.mkdir(parents=True)
        self.parent = self.public.parent / ".htaccess"
        self.child = self.public / ".htaccess"
        self.original_parent = b"RewriteEngine On\r\nRewriteRule ^$ index.php [L]\r\n# keep other rules\r\n"
        self.original_child = b'PassengerAppRoot "/private/app"\nPassengerBaseURI "/stress"\n'
        self.parent.write_bytes(self.original_parent)
        self.child.write_bytes(self.original_child)
        (self.public / "index.php").write_bytes(b"original bike PHP application")
        (self.public / "loader.php").write_bytes(b"existing CAESAR loader")
        self.dist = self.home / "caesar-system/dist"
        (self.dist / "assets").mkdir(parents=True)
        self.frontend = b'<title>CAESAR</title><script src="./assets/index-test.js"></script>'
        (self.dist / "index.html").write_bytes(self.frontend)
        (self.dist / "assets/index-test.js").write_bytes(b"public frontend JavaScript")
        self.app = self.home / "caesar-system"
        self.app.chmod(0o700)
        self.data = self.home / "caesar-data"
        self.data.mkdir()
        (self.data / "drawing.pdf").write_bytes(b"private drawing retained")
        self.mode = "success"
        self.restarts = 0

    def tearDown(self):
        self.temp.cleanup()

    def fetch(self, url):
        if url == "https://easyai.com.au/":
            return 200, b"unchanged main website"
        if url.endswith("loader.php"):
            return 200, (self.public / "loader.php").read_bytes()
        if "api/v1/health" in url:
            healthy = self.mode == "success" or self.mode == "explicit" and b"PassengerAppType wsgi" in self.child.read_bytes()
            return (200, json.dumps({"mode": "authenticated"}).encode()) if healthy else (404, b"server HTML 404")
        return 200, (self.public / "index.html").read_bytes()

    def restart(self):
        self.restarts += 1

    def run_repair(self):
        repair = routing.Repair(self.home, fetch=self.fetch, restart=self.restart)
        with redirect_stdout(io.StringIO()), patch.object(routing.time, "sleep"):
            repair.run()
        return repair

    def assert_restored(self):
        self.assertEqual(self.parent.read_bytes(), self.original_parent)
        self.assertEqual(self.child.read_bytes(), self.original_child)
        self.assertEqual((self.public / "index.php").read_bytes(), b"original bike PHP application")
        self.assertFalse((self.public / "index.html").exists())
        self.assertFalse((self.public / "assets").exists())
        self.assertEqual((self.data / "drawing.pdf").read_bytes(), b"private drawing retained")
        self.assertEqual(self.app.stat().st_mode & 0o777, 0o700)

    def test_scoped_repair_keeps_php_and_backs_up_exact_routing_bytes(self):
        repair = self.run_repair()
        self.assertEqual(self.restarts, 1)
        self.assertTrue(self.parent.read_bytes().endswith(self.original_parent))
        self.assertIn(b"DirectoryIndex index.html", self.child.read_bytes())
        self.assertEqual((self.public / "index.php").read_bytes(), b"original bike PHP application")
        self.assertEqual((self.public / "index.html").read_bytes(), self.frontend)
        self.assertEqual(self.app.stat().st_mode & 0o777, 0o711)
        self.assertEqual((repair.backup / "easyai.com.au/.htaccess").read_bytes(), self.original_parent)
        self.assertEqual((repair.backup / "easyai.com.au/stress/.htaccess").stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.public / "passenger_wsgi.py").exists())
        self.assertEqual((self.data / "drawing.pdf").read_bytes(), b"private drawing retained")

    def test_explicit_wsgi_fallback_is_idempotent(self):
        self.mode = "explicit"
        self.run_repair()
        first = self.parent.read_bytes()
        self.run_repair()
        self.assertEqual(self.parent.read_bytes(), first)
        self.assertEqual(self.child.read_bytes().count(b"CAESAR ROUTING REPAIR BEGIN"), 1)
        self.assertIn(b"PassengerAppType wsgi", self.child.read_bytes())

    def test_unavailable_server_restores_every_changed_public_file(self):
        self.mode = "unavailable"
        with self.assertRaisesRegex(routing.RepairError, "unavailable"):
            self.run_repair()
        self.assert_restored()
        self.assertFalse(list(self.public.rglob(".htaccess.caesar-*")))

    def test_restart_failure_restores_routing_and_frontend(self):
        self.restart = lambda: (_ for _ in ()).throw(routing.RepairError("restart failed"))
        with self.assertRaisesRegex(routing.RepairError, "restart failed"):
            self.run_repair()
        self.assert_restored()

    def test_loader_mapping_mismatch_prevents_any_write(self):
        repair = routing.Repair(self.home, fetch=lambda url: (200, b"different loader"), restart=self.restart)
        with self.assertRaisesRegex(routing.RepairError, "does not match"):
            repair.run()
        self.assert_restored()
        self.assertFalse(repair.backup.exists())
        self.assertEqual(self.restarts, 0)

    def test_parent_bypass_matches_only_stress_app(self):
        self.run_repair()
        content = self.parent.read_text()
        pattern = re.search(r"RewriteRule (\S+) - \[L\]", content)[1]
        for path in ("stress", "stress/", "stress/api/v1/health"):
            self.assertTrue(re.match(pattern, path))
        for path in ("", "index.php", "stressful", "stress-test/", "other/stress/"):
            self.assertIsNone(re.match(pattern, path))
