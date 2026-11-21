"""Account-level CloudLinux installer for the tested CAESAR /stress/ package.

Run this file normally in cPanel Terminal, not through a pipe: credentials are
prompted interactively. No sudo, Docker, Node.js or git is required on hosting.
"""

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
from http.cookiejar import CookieJar
import io
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import secrets
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler, urlopen
import zipfile

BUNDLE_URL = "https://raw.githubusercontent.com/efrgdgr0024345/stress/c4580c92987349688a8b50cd3a9c73d13620648d/downloads/caesar-cpanel.zip"
BUNDLE_SHA256 = "5632d129ffa72961aba813097adb76483adcba532c224c58adcaac7e52638bd2"
APP_NAME = "caesar-system"


class InstallError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        # In particular, never redirect an administrator login to another URL.
        return None


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        stream.write(content)


def unpack_bundle(content, expected=BUNDLE_SHA256):
    if hashlib.sha256(content).hexdigest() != expected:
        raise InstallError("Package checksum does not match the reviewed release; nothing installed.")
    files = {}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or path.parts[0] != APP_NAME or len(path.parts) < 2:
                raise InstallError("Unsafe package path; nothing installed.")
            if entry.is_dir() or entry.external_attr >> 28 == 0o12:
                raise InstallError("Unexpected directory/link in package; nothing installed.")
            name = path.relative_to(APP_NAME).as_posix()
            if name in files:
                raise InstallError("Duplicate package path; nothing installed.")
            files[name] = archive.read(entry)
    manifest = json.loads(files["MANIFEST.json"])
    if set(files) != set(manifest["files"]) | {"MANIFEST.json"}:
        raise InstallError("Package manifest does not match its files.")
    for name, digest in manifest["files"].items():
        if hashlib.sha256(files[name]).hexdigest() != digest:
            raise InstallError("Package manifest hash mismatch.")
    return files


class Selector:
    def __init__(self, executable, log_directory):
        self.executable = executable
        self.logs = log_directory

    def call(self, action, *arguments):
        print(f"CloudLinux: {action} …", flush=True)
        try:
            result = subprocess.run(
                [self.executable, action, "--json", "--interpreter", "python", *arguments],
                capture_output=True, text=True, timeout=1200,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InstallError(f"CloudLinux {action} did not complete ({type(exc).__name__}).") from None
        try:
            payload = json.loads(result.stdout)
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        if result.returncode or payload.get("result") != "success":
            # Do not print arbitrary Selector output: it can include environment
            # variables belonging to an existing application.
            path = self.logs / f"selector-{action}-{secrets.token_hex(3)}.log"
            private_write(path, result.stdout + "\n" + result.stderr)
            raise InstallError(f"CloudLinux {action} failed. Private diagnostic log: {path}")
        return payload


def applications(payload, username):
    found = []
    for version, details in payload.get("available_versions", {}).items():
        for name, app in details.get("users", {}).get(username, {}).get("applications", {}).items():
            found.append((version, name, app))
    return found


class Installer:
    def __init__(self, home, domain, uri, public_directory=None, selector=None):
        self.home = home.resolve()
        self.domain = domain
        self.uri = uri.strip("/")
        self.url = f"https://{domain}/{self.uri}/"
        self.app = self.home / APP_NAME
        self.settings = self.home / ".config/caesar/caesar-system.json"
        self.public = Path(public_directory).expanduser() if public_directory else None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
        self.backup = self.home / "caesar-backups" / stamp
        if (self.home / "caesar-backups").is_symlink():
            raise InstallError("The private backup directory must not be a symlink.")
        self.username = pwd.getpwuid(os.getuid()).pw_name
        if selector is None:
            executable = shutil.which("cloudlinux-selector")
            if not executable:
                executable = next((p for p in ("/usr/bin/cloudlinux-selector", "/usr/sbin/cloudlinux-selector") if os.access(p, os.X_OK)), None)
            if not executable:
                raise InstallError("CloudLinux Selector is not accessible from this shell.")
            selector = Selector(executable, self.backup)
        self.selector = selector

    def public_directory(self):
        if self.public is None:
            candidates = [self.home / "public_html" / self.uri,
                          self.home / self.domain / self.uri,
                          self.home / "public_html" / self.domain / self.uri,
                          self.home / "domains" / self.domain / "public_html" / self.uri]
            candidates = list(dict.fromkeys(p.resolve() for p in candidates if (p / "loader.php").is_file()))
            if len(candidates) == 1:
                self.public = candidates[0]
            else:
                value = input("Full filesystem path of your existing public stress folder: ").strip()
                self.public = Path(value).expanduser()
        self.public = self.public.resolve()
        if not self.public.is_relative_to(self.home) or not self.public.is_dir() or self.public == self.home:
            raise InstallError("The public stress folder must be an existing directory inside your hosting home.")
        if self.app.is_relative_to(self.public) or self.public.is_relative_to(self.app):
            raise InstallError("Application code must be separate from the public stress folder.")
        for name in ("loader.php", "LESSONS_LEARNED.md", ".htaccess"):
            if (self.public / name).is_symlink():
                raise InstallError(f"Refusing a symlink in the public folder: {name}")
        print(f"Public URL: {self.url}\nPublic folder: {self.public}\nPrivate application: {self.app}", flush=True)
        # Verify this filesystem directory actually corresponds to the requested
        # URL, rather than guessing an add-on domain's document root.
        name = "caesar-check-" + secrets.token_hex(12) + ".txt"
        token = secrets.token_hex(24)
        probe = self.public / name
        created = False
        try:
            with probe.open("x") as stream:
                created = True
                stream.write(token)
            probe.chmod(0o644)
            with build_opener(NoRedirect()).open(self.url + name, timeout=20) as response:
                if response.read(1024).decode() != token:
                    raise InstallError("Public folder does not match the website URL; no routing changed.")
        except (OSError, URLError) as exc:
            raise InstallError(f"Could not verify the public folder ({type(exc).__name__}); no routing changed.") from None
        finally:
            if created:
                probe.unlink(missing_ok=True)

    def save(self, path, relative):
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise InstallError(f"Refusing to replace a non-regular file: {path}")
            target = self.backup / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(path, target)
            target.chmod(0o600)

    def write_application(self, files):
        if self.app.is_symlink() or (self.app.exists() and not self.app.is_dir()):
            raise InstallError("Private application path is not a regular directory.")
        self.app.mkdir(exist_ok=True, mode=0o700)
        for name, data in files.items():
            path = self.app / name
            if any(parent.is_symlink() for parent in [path, *path.parents] if parent != self.home):
                raise InstallError("Refusing a symlink inside the application directory.")
            if not path.resolve().is_relative_to(self.app):
                raise InstallError("An application path points outside the private directory.")
            if path.is_file() and not path.is_symlink() and path.read_bytes() == data:
                continue
            self.save(path, Path("application") / name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o644)

    def configure(self):
        resolved = self.settings.resolve()
        if not resolved.is_relative_to(self.home) or resolved.is_relative_to(self.public) or "public_html" in resolved.parts:
            raise InstallError("Credential configuration must stay outside public directories.")
        if not self.settings.exists():
            subprocess.run([sys.executable, str(self.app / "scripts/configure_cpanel.py")], check=True)
        if self.settings.is_symlink() or self.settings.stat().st_mode & 0o077:
            raise InstallError("Private configuration must be a regular file with permissions 600.")
        settings = json.loads(self.settings.read_text())
        if not settings.get("CAESAR_ADMIN_EMAIL") or len(settings.get("CAESAR_ADMIN_PASSWORD", "")) < 12:
            raise InstallError("Private administrator configuration is missing or invalid.")
        if settings.get("CAESAR_LOCAL_DEMO") != "0" or settings.get("CAESAR_SECURE_COOKIE") != "1":
            raise InstallError("Hosted configuration must disable demo access and require secure cookies.")
        if not Path(settings.get("CAESAR_DATA_DIR", "")).is_absolute():
            raise InstallError("Drawing storage must use an absolute private path.")
        data = Path(settings["CAESAR_DATA_DIR"]).resolve()
        if not data.is_relative_to(self.home) or data.is_relative_to(self.app) or data.is_relative_to(self.public) or "public_html" in data.parts or data == self.home:
            raise InstallError("Drawing storage must be private, outside public and application directories.")
        return settings

    def run(self, files):
        state = self.selector.call("get", "--user", self.username)
        if state.get("selector_enabled") is not True:
            raise InstallError("Python Selector is not enabled for this hosting account.")
        existing = None
        for version, name, app in applications(state, self.username):
            same_root = (self.home / name).resolve() == self.app
            same_url = app.get("domain") == self.domain and app.get("app_uri", "").strip("/") == self.uri
            if same_root != same_url:
                raise InstallError("An existing Python app conflicts with this application root or URL; kept unchanged.")
            if same_root:
                if not str(version).startswith("3.12") or app.get("startup_file") != "passenger_wsgi.py" or app.get("entry_point") != "application":
                    raise InstallError("The existing app uses different runtime settings; kept unchanged.")
                if app.get("env_vars"):
                    raise InstallError("The existing app has environment overrides. Review them before using the account-private configuration.")
                existing = app
        self.public_directory()
        self.backup.mkdir(parents=True, mode=0o700, exist_ok=True)
        for name in (".htaccess", "loader.php", "LESSONS_LEARNED.md"):
            self.save(self.public / name, Path("public") / name)
        print(f"Private backups: {self.backup}", flush=True)
        if existing:
            self.selector.call("stop", "--domain", self.domain, "--app-root", APP_NAME)
        # Runtime data/configuration are never extracted or overwritten.
        self.write_application(files)
        settings = self.configure()
        data = Path(settings["CAESAR_DATA_DIR"])
        if data.exists():
            shutil.copytree(data, self.backup / "private-data", symlinks=True)
        if not existing:
            self.selector.call("create", "--domain", self.domain, "--app-root", APP_NAME,
                               "--app-uri", self.uri, "--version", "3.12",
                               "--startup-file", "passenger_wsgi.py", "--entry-point", "application")
            # Some providers create a starter WSGI template during registration.
            # Restore the reviewed entry point, preserving that template first.
            startup = self.app / "passenger_wsgi.py"
            if not startup.exists() or startup.read_bytes() != files["passenger_wsgi.py"]:
                self.save(startup, Path("provider-startup-template.py"))
                startup.write_bytes(files["passenger_wsgi.py"])
        self.selector.call("install-modules", "--domain", self.domain, "--app-root", APP_NAME,
                           "--requirements-file", "requirements-cpanel.txt")
        for name in ("loader.php", "LESSONS_LEARNED.md"):
            (self.public / name).write_bytes(files[name])
            (self.public / name).chmod(0o644)
        self.selector.call("restart", "--domain", self.domain, "--app-root", APP_NAME)
        self.verify(settings)
        print(f"\nREADY: {self.url}\nSign in with the administrator email and password you configured.")
        print("Keep this engineering-review pilot access-restricted as described in docs/CPANEL.md.")

    def verify(self, settings):
        opener = build_opener(NoRedirect(), HTTPCookieProcessor(CookieJar()))
        for attempt in range(15):
            try:
                with opener.open(self.url + "api/v1/health", timeout=10) as response:
                    status = json.load(response)
                if status.get("mode") == "authenticated":
                    break
                raise InstallError("Hosted API is not in authenticated mode; restrict the URL and check configuration.")
            except (OSError, URLError, ValueError):
                if attempt == 14:
                    raise InstallError("Python application did not become healthy. Check the private Passenger error log and hosting resource limits.") from None
                print("Waiting for Passenger startup …", flush=True)
                time.sleep(2)
        from urllib.request import Request
        payload = json.dumps({"email": settings["CAESAR_ADMIN_EMAIL"], "password": settings["CAESAR_ADMIN_PASSWORD"]}).encode()
        try:
            with opener.open(Request(self.url + "api/v1/auth/login", data=payload, headers={"Content-Type": "application/json"}), timeout=20) as response:
                if response.status != 200:
                    raise InstallError("Administrator login failed.")
            with opener.open(self.url + "api/v1/projects", timeout=20) as response:
                if not isinstance(json.load(response), list):
                    raise InstallError("Authenticated project request failed.")
            with opener.open(Request(self.url + "api/v1/auth/logout", data=b""), timeout=20) as response:
                response.read()
        except (OSError, URLError, ValueError):
            raise InstallError("API is running, but administrator login verification failed. Existing database passwords are not reset by this installer.") from None
        print("Verified authenticated API, administrator login and project access.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", default="easyai.com.au")
    parser.add_argument("--uri", default="stress")
    parser.add_argument("--public-dir", help="Existing public stress directory, only needed if automatic discovery is inconclusive")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12) or sys.platform != "linux":
        raise InstallError("Run with your hosting account's Python 3.12 on Linux.")
    if not args.domain or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in args.domain):
        raise InstallError("Invalid domain.")
    if not args.uri.strip("/") or any(not part or part in (".", "..") for part in args.uri.strip("/").split("/")) or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/" for c in args.uri):
        raise InstallError("Use a simple nonempty application URL path such as stress.")
    print("Downloading and verifying the reviewed application package …", flush=True)
    with urlopen(BUNDLE_URL, timeout=60) as response:
        content = response.read(10 * 1024 * 1024)
    Installer(Path.home(), args.domain, args.uri, args.public_dir).run(unpack_bundle(content))


if __name__ == "__main__":
    try:
        main()
    except (InstallError, OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile, KeyboardInterrupt) as exc:
        if isinstance(exc, InstallError):
            print(f"\nSETUP STOPPED: {exc}", file=sys.stderr)
        else:
            print(f"\nSETUP STOPPED ({type(exc).__name__}). Existing data and private configuration are retained.", file=sys.stderr)
        raise SystemExit(1)
