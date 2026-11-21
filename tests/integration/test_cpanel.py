"""Exercise the downloadable package through its actual WSGI entry point."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]


class CpanelPackageTests(unittest.TestCase):
    def test_extracted_package_https_auth_upload_export_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            with zipfile.ZipFile(ROOT / "downloads/caesar-cpanel.zip") as archive:
                names = archive.namelist()
                self.assertFalse(any(part in {".git", ".local", ".env", ".venv", "node_modules", "__pycache__"} for name in names for part in Path(name).parts))
                archive.extractall(temp)
            application = temp / "caesar-system"
            manifest = json.loads((application / "MANIFEST.json").read_text())
            for name, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256((application / name).read_bytes()).hexdigest(), digest)
                if name != "public/.gitkeep":
                    self.assertEqual((application / name).read_bytes(), (ROOT / name).read_bytes(), f"Rebuild stale package: {name}")
            env = {**os.environ, "CAESAR_DATA_DIR": str(temp / "data"),
                   "CAESAR_ADMIN_EMAIL": "test@example.invalid", "CAESAR_ADMIN_PASSWORD": "isolated-test-password-987",
                   "CAESAR_LOCAL_DEMO": "0", "CAESAR_SECURE_COOKIE": "1", "PYTHONPATH": ""}
            code = '''
import io, os, zipfile
import httpx, fitz
from passenger_wsgi import application
mount = os.environ.get("CAESAR_TEST_MOUNT", "")
def mounted(environ, start_response):
    assert environ["PATH_INFO"].startswith(mount + "/")
    environ["SCRIPT_NAME"] = mount
    environ["PATH_INFO"] = environ["PATH_INFO"][len(mount):]
    return application(environ, start_response)
with httpx.Client(transport=httpx.WSGITransport(app=mounted), base_url="https://test.invalid" + mount + "/") as client:
    assert client.get("/api/v1/health").json()["mode"] == "authenticated"
    assert client.get("/").status_code == 200
    assert "Install on cPanel" in client.get("/loader.php").text
    assert client.get("/api/v1/projects").status_code == 401
    assert client.post("/api/v1/auth/local").status_code == 403
    result = client.post("/api/v1/auth/login", json={"email":"test@example.invalid", "password":"isolated-test-password-987"})
    assert result.status_code == 200, result.text
    assert "Secure" in result.headers["set-cookie"] and "HttpOnly" in result.headers["set-cookie"]
    assert "Path=" + mount + "/;" in result.headers["set-cookie"]
    assert client.get("/api/v1/projects").json() == []
    project = client.post("/api/v1/projects", json={"title":"WSGI deployment test", "line_id":"TEST-01"}).json()
    doc = fitz.open()
    doc.new_page(width=600, height=500).insert_text((70, 80), "Non-sensitive deployment fixture")
    source = doc.tobytes()
    doc.close()
    result = client.post(f"/api/v1/projects/{project['id']}/sources?version={project['version']}", files={"file":("fixture.pdf",source,"application/pdf")})
    assert result.status_code == 200, result.text
    project = result.json()
    result = client.post(f"/api/v1/projects/{project['id']}/nodes", json={"version":project["version"], "line_id":"TEST-01", "route":"main", "order":1, "kind":"support", "dimension":"100 mm", "evidence":"Synthetic deployment test", "instances":[{"sheet_id":project["sheets"][0]["id"], "anchor":[100,120], "bubble":[150,100]}]})
    assert result.status_code == 200, result.text
    project = result.json()
    result = client.post(f"/api/v1/projects/{project['id']}/exports", json={"version":project["version"]})
    assert result.status_code == 200, result.text
    bundle = client.get(f"/api/v1/projects/{project['id']}/artifacts/{result.json()['id']}/download")
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert any(name.endswith(".pdf") for name in archive.namelist())
    for path in ("/.env", "/.git/config", "/passenger_wsgi.py", "/requirements.txt", "/.local/workspace.sqlite3"):
        assert client.get(path).status_code == 404, path
    result = client.post("/api/v1/auth/logout")
    assert "Path=" + mount + "/;" in result.headers["set-cookie"]
    assert client.get("/api/v1/projects").status_code == 401
print("WSGI package: HTTPS login, upload, export and private paths verified")
'''
            for mount in ("", "/stress"):
                result = subprocess.run([sys.executable, "-c", code], cwd=application, env={**env, "CAESAR_TEST_MOUNT": mount, "CAESAR_DATA_DIR": str(temp / ("root-data" if not mount else "mount-data"))}, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            configure = '''
from unittest.mock import patch
import runpy
with patch("builtins.input", return_value="test@example.invalid"), patch("getpass.getpass", return_value="isolated-test-password-987"):
    runpy.run_path("scripts/configure_cpanel.py", run_name="__main__")
'''
            result = subprocess.run([sys.executable, "-c", configure], cwd=application, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("isolated-test-password-987", result.stdout + result.stderr)
            settings = temp / ".config/caesar/caesar-system.json"
            self.assertEqual(settings.stat().st_mode & 0o777, 0o600)
            private_env = {key: value for key, value in env.items() if not key.startswith("CAESAR_")}
            result = subprocess.run([sys.executable, "-c", code], cwd=application, env={**private_env, "CAESAR_TEST_MOUNT": "/stress"}, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            settings.chmod(0o644)
            result = subprocess.run([sys.executable, "-c", "import passenger_wsgi"], cwd=application, env=private_env, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            settings.chmod(0o600)
            previous = settings.read_bytes()
            result = subprocess.run([sys.executable, "-c", configure], cwd=application, env=env, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(settings.read_bytes(), previous)
            for changed in ({"CAESAR_LOCAL_DEMO": "1"}, {"CAESAR_ADMIN_PASSWORD": ""}, {"CAESAR_SECURE_COOKIE": "0"}, {"CAESAR_DATA_DIR": str(application / "public/data")}):
                result = subprocess.run([sys.executable, "-c", "import passenger_wsgi"], cwd=application, env={**env, **changed}, capture_output=True, text=True, timeout=15)
                self.assertNotEqual(result.returncode, 0, changed.keys())
