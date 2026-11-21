"""Report hosting routing and isolated Python startup without exposing secrets."""

import html
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def redact(text, settings):
    for name, value in settings.items():
        if any(part in name.lower() for part in ("password", "token", "secret")) and value:
            text = text.replace(str(value), "[REDACTED]")
    return text


def routing_lines(text):
    allowed = {"passengerapproot", "passengerbaseuri", "passengerpython", "passengerstartupfile", "passengerappentrypoint", "passengerappenv", "passengerapptype", "passengerenabled", "passengerlogfile", "passengerfriendlyerrorpages", "directoryindex", "sethandler", "addhandler", "rewriteengine", "rewritebase"}
    for line in text.splitlines():
        words = line.strip().split(None, 1)
        if re.fullmatch(r"</?IfModule(?:\s+!?[\w.-]+)?>", line.strip(), re.I):
            yield line.strip()
        elif words and words[0].lower() in allowed:
            yield line.strip()
        elif words and words[0].lower() in {"rewriterule", "rewritecond"}:
            # Query strings/redirect targets in rules can contain credentials.
            yield words[0] + " [present; values omitted]"


def main():
    home = Path.home()
    app = home / "caesar-system"
    settings_file = home / ".config/caesar/caesar-system.json"
    settings = {}
    if settings_file.is_file():
        settings = json.loads(settings_file.read_text())
    print("Private configuration:", "present" if settings else "missing")
    if settings_file.exists():
        print("Configuration permissions:", oct(settings_file.stat().st_mode & 0o777))
    public_candidates = [home / "public_html/stress", home / "easyai.com.au/stress", home / "public_html/easyai.com.au/stress", home / "domains/easyai.com.au/public_html/stress", Path.cwd()]
    public_candidates = list(dict.fromkeys(p.resolve() for p in public_candidates if p != app and (p / "loader.php").is_file()))
    interpreters = []
    for public in public_candidates:
        print("\nPublic folder:", public)
        print("Existing index files:", ", ".join(name for name in ("index.php", "index.html", "index.htm") if (public / name).is_file()) or "none")
        for path in (public / ".htaccess", public.parent / ".htaccess"):
            print("Routing file:", path, "present" if path.is_file() else "missing")
            if path.is_file():
                for line in routing_lines(path.read_text(errors="replace")):
                    print(" ", redact(line, settings))
                    if line.lower().startswith("passengerpython "):
                        words = shlex.split(line)
                        if len(words) == 2:
                            interpreters.append(Path(words[1]))
    print("\nPublic HTTP checks:")
    for path in ("api/v1/health", "", "loader.php"):
        url = "https://easyai.com.au/stress/" + path
        try:
            response = urlopen(url, timeout=15)
        except HTTPError as exc:
            response = exc
        except (OSError, URLError) as exc:
            print(url, type(exc).__name__)
            continue
        with response:
            text = response.read(200000).decode(errors="replace")
            title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
            summary = " title=" + re.sub(r"\s+", " ", html.unescape(title[1])).strip()[:140] if title else ""
            print(url, response.code, response.headers.get("Content-Type", ""), redact(summary, settings))
    interpreters.extend(sorted((home / "virtualenv/caesar-system").glob("*/bin/python")))
    interpreter = next((p for p in interpreters if p.is_file()), None)
    if not interpreter:
        print("\nApplication virtual-environment Python: NOT FOUND")
        return
    print("\nApplication interpreter:", interpreter)
    code = '''
import sys
import resource
print("Runtime:", sys.version.split()[0])
print("Process address-space limit:", resource.getrlimit(resource.RLIMIT_AS))
from passenger_wsgi import application
print("WSGI startup: PASS")
import httpx
with httpx.Client(transport=httpx.WSGITransport(app=application), base_url="https://diagnostic.invalid") as client:
    result = client.get("/api/v1/health")
    print("Internal API health:", result.status_code, result.json().get("mode"))
'''
    # Preserve real projects and credentials: bootstrap against a disposable,
    # private database, while using the actual installed dependency environment.
    import os
    with tempfile.TemporaryDirectory(prefix="caesar-diagnostic-") as temporary:
        environment = {**os.environ, "CAESAR_DATA_DIR": str(Path(temporary) / "data"), "CAESAR_LOCAL_DEMO": "0", "CAESAR_SECURE_COOKIE": "1"}
        try:
            result = subprocess.run([str(interpreter), "-c", code], cwd=app, env=environment, capture_output=True, text=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print("WSGI startup:", type(exc).__name__)
            return
        print(redact(result.stdout, settings).strip())
        if result.returncode:
            print("WSGI startup: FAILED; exception follows (configuration secrets redacted)")
            print(redact(result.stderr, settings)[-6000:])
        else:
            print("Application starts in this interpreter. Compare the web-server mapping above with the public HTTP results.")
    print("\nNo real projects, passwords or routing files were changed.")


if __name__ == "__main__":
    main()
