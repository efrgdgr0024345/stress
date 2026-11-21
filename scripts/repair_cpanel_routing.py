"""Repair only EasyAI's /stress/ mapping, with private backups and rollback."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPRedirectHandler, Request


class RepairError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def request(url):
    try:
        response = build_opener(NoRedirect()).open(Request(url, headers={"Cache-Control": "no-cache"}), timeout=15)
    except HTTPError as exc:
        response = exc
    with response:
        return response.code, response.read(2000000)


def marked_block(original, content):
    pattern = rb"(?ms)^# CAESAR ROUTING REPAIR BEGIN\r?\n.*?^# CAESAR ROUTING REPAIR END\r?\n?"
    remainder = re.sub(pattern, b"", original)
    return b"# CAESAR ROUTING REPAIR BEGIN\n" + content + b"# CAESAR ROUTING REPAIR END\n" + remainder


class Repair:
    def __init__(self, home, public=None, fetch=request, restart=None):
        self.home = Path(home).resolve()
        self.public = Path(public).expanduser().resolve() if public else self.home / "easyai.com.au/stress"
        self.app = self.home / "caesar-system"
        self.url = "https://easyai.com.au/stress/"
        self.fetch = fetch
        self.restart = restart or self.restart_application
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-routing-" + secrets.token_hex(3)
        self.backup = self.home / "caesar-backups" / stamp
        self.originals = {}
        self.created_directories = []
        self.original_domain = None
        self.last_status = None
        self.app_original_mode = None

    def validate(self):
        if not self.public.is_relative_to(self.home) or self.public == self.home or not self.public.is_dir() or self.public.name != "stress":
            raise RepairError("Use the existing public stress folder inside your hosting home.")
        if self.app.is_relative_to(self.public) or self.public.is_relative_to(self.app):
            raise RepairError("The private application must be outside the public folder.")
        if self.app.is_symlink() or not self.app.is_dir():
            raise RepairError("The private application must be a regular directory.")
        if (self.home / "caesar-backups").is_symlink():
            raise RepairError("The private backup directory must not be a symlink.")
        for path in (self.public / ".htaccess", self.public.parent / ".htaccess"):
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise RepairError("A routing file is not a regular file; nothing changed.")
        if not (self.app / "dist/index.html").is_file() or not (self.public / "loader.php").is_file():
            raise RepairError("The installed application or existing loader is missing.")
        # Confirm this is the actual public URL before touching either routing
        # file. The installed loader is HTML served identically by PHP/Python.
        code, body = self.fetch(self.url + "loader.php")
        if code != 200 or hashlib.sha256(body).digest() != hashlib.sha256((self.public / "loader.php").read_bytes()).digest():
            raise RepairError("Public folder does not match the live loader; nothing changed.")
        self.original_domain = self.fetch("https://easyai.com.au/")
        self.backup.mkdir(parents=True, mode=0o700)
        print(f"Private routing backup: {self.backup}", flush=True)

    def atomic_write(self, path, content, mode):
        missing = []
        parent = path.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for directory in reversed(missing):
            directory.mkdir()
            self.created_directories.append(directory)
        handle, temporary = tempfile.mkstemp(prefix=".htaccess.caesar-", dir=path.parent)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(content)
            os.replace(temporary, path)
            path.chmod(mode)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def write(self, path, content):
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(self.home)):
            raise RepairError("A target is a symlink; refusing to replace it.")
        if path.exists() and not path.is_file():
            raise RepairError("A target is not a regular file; refusing to replace it.")
        if path not in self.originals:
            old = path.read_bytes() if path.is_file() else None
            mode = path.stat().st_mode & 0o777 if old is not None else 0o644
            self.originals[path] = (old, mode)
            if old is not None:
                destination = self.backup / path.relative_to(self.home)
                destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                with open(destination, "xb", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
                    stream.write(old)
        self.atomic_write(path, content, self.originals[path][1])

    def restore(self):
        failures = []
        for path, (content, mode) in reversed(list(self.originals.items())):
            try:
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    self.atomic_write(path, content, mode)
            except OSError:
                failures.append(str(path))
        for directory in reversed(self.created_directories):
            try:
                directory.rmdir()
            except OSError:
                pass
        if self.app_original_mode is not None:
            try:
                self.app.chmod(self.app_original_mode)
            except OSError:
                failures.append(str(self.app))
        if failures:
            raise RepairError(f"Automatic restore could not replace {len(failures)} file(s). Restore them from the private backup: {self.backup}")
        print("Previous routing and public files restored. Private application, credentials and drawings retained.", flush=True)

    def restart_application(self):
        executable = shutil.which("cloudlinux-selector") or next((p for p in ("/usr/bin/cloudlinux-selector", "/usr/sbin/cloudlinux-selector") if os.access(p, os.X_OK)), None)
        if not executable:
            raise RepairError("CloudLinux Selector is not accessible.")
        result = subprocess.run([executable, "restart", "--json", "--interpreter", "python", "--domain", "easyai.com.au", "--app-root", "caesar-system"], capture_output=True, text=True, timeout=120)
        try:
            success = json.loads(result.stdout).get("result") == "success"
        except (ValueError, AttributeError):
            success = False
        if result.returncode or not success:
            raise RepairError("CloudLinux restart did not succeed; no raw environment output printed.")

    def healthy(self):
        try:
            status, body = self.fetch(self.url + "api/v1/health?caesar-routing-check=" + secrets.token_hex(6))
            self.last_status = status
            payload = json.loads(body) if status == 200 else {}
            if status != 200 or not isinstance(payload, dict) or payload.get("mode") != "authenticated":
                print(f"Public API check: HTTP {status}", flush=True)
                return False
            status, body = self.fetch(self.url + "?caesar-routing-check=" + secrets.token_hex(6))
            source = (self.app / "dist/index.html").read_bytes()
            assets = re.findall(rb'(?:src|href)=["\'][^"\']*(assets/[^"\']+)["\']', source)
            if status != 200 or not assets or not all(asset in body for asset in assets):
                print(f"Public frontend check: HTTP {status}, expected CAESAR assets not found", flush=True)
                return False
            after_status, _ = self.fetch("https://easyai.com.au/")
            if after_status != self.original_domain[0]:
                raise RepairError("Main-domain response status changed; restoring the previous configuration.")
            return True
        except (URLError, OSError, ValueError):
            print("Public request could not be verified.", flush=True)
            return False

    def run(self):
        self.validate()
        parent = self.public.parent / ".htaccess"
        child = self.public / ".htaccess"
        parent_content = parent.read_bytes() if parent.exists() else b""
        child_content = child.read_bytes() if child.exists() else b""
        try:
            self.app_original_mode = self.app.stat().st_mode & 0o777
            with open(self.backup / "application-directory-mode.json", "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
                json.dump({"path": str(self.app), "original_mode": oct(self.app_original_mode)}, stream)
            self.app.chmod(self.app_original_mode | 0o011)
            # This bypass applies only to this app, before the domain's existing
            # rewrite rules. Other domain rules remain byte-for-byte intact.
            self.write(parent, marked_block(parent_content, b"<IfModule mod_rewrite.c>\nRewriteEngine On\nRewriteRule ^stress(?:/|$) - [L]\n</IfModule>\n"))
            # Prefer the built website while keeping index.php intact. Only
            # public frontend assets are copied; no Python/config/data files.
            for source in sorted((self.app / "dist").rglob("*")):
                if source.is_file():
                    if source.is_symlink():
                        raise RepairError("A frontend source is a symlink.")
                    self.write(self.public / source.relative_to(self.app / "dist"), source.read_bytes())
            for explicit in (False, True):
                flags = b"DirectoryIndex index.html\n"
                if explicit:
                    flags += b"PassengerEnabled on\nPassengerAppType wsgi\nPassengerStartupFile passenger_wsgi.py\n"
                self.write(child, marked_block(child_content, flags))
                print("Checking explicit WSGI routing …" if explicit else "Checking scoped rewrite and frontend routing …", flush=True)
                self.restart()
                for attempt in range(3):
                    if self.healthy():
                        print("READY: https://easyai.com.au/stress/\nSign in with your existing administrator credentials.")
                        print("Original PHP index retained. Backups are private. Pilot access restrictions still apply.")
                        return
                    if attempt < 2:
                        time.sleep(2)
            raise RepairError(f"Live API/frontend unavailable after the routing checks (last API status: {self.last_status}). Previous files have been restored. Ask the provider to check Python/WSGI mapping for easyai.com.au/stress and private application startup logs.")
        except BaseException:
            self.restore()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", help="Default: ~/easyai.com.au/stress, as confirmed by the hosting diagnostic")
    args = parser.parse_args()
    Repair(Path.home(), args.public_dir).run()


if __name__ == "__main__":
    try:
        main()
    except (RepairError, OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        print("\nREPAIR STOPPED: " + (str(exc) if isinstance(exc, RepairError) else type(exc).__name__))
        raise SystemExit(1)
