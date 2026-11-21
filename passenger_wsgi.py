"""cPanel Passenger entry point for a private HTTPS pilot (not PHP execution)."""

import os
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Optional account-private CLI configuration. Environment variables take
# precedence. Secrets never belong in the public loader or process arguments.
settings = ROOT.parent / ".config" / "caesar" / f"{ROOT.name}.json"
if settings.is_file():
    if settings.stat().st_mode & 0o077:
        raise RuntimeError("Private CAESAR configuration must have mode 600.")
    values = json.loads(settings.read_text())
    for key in ("CAESAR_DATA_DIR", "CAESAR_ADMIN_EMAIL", "CAESAR_ADMIN_PASSWORD", "CAESAR_LOCAL_DEMO", "CAESAR_SECURE_COOKIE"):
        if key in values:
            os.environ.setdefault(key, str(values[key]))

if os.environ.get("CAESAR_LOCAL_DEMO", "0") != "0":
    raise RuntimeError("Hosted installations require CAESAR_LOCAL_DEMO=0.")
if os.environ.get("CAESAR_SECURE_COOKIE", "1") != "1":
    raise RuntimeError("Hosted installations require HTTPS and secure cookies.")
os.environ["CAESAR_LOCAL_DEMO"] = "0"
os.environ["CAESAR_SECURE_COOKIE"] = "1"

data_value = os.environ.get("CAESAR_DATA_DIR", "")
data = Path(data_value).resolve()
if not data_value or not Path(data_value).is_absolute() or data.is_relative_to(ROOT) or "public_html" in data.parts:
    raise RuntimeError("Set CAESAR_DATA_DIR to an absolute private directory outside the application and public_html.")
if not os.environ.get("CAESAR_ADMIN_EMAIL", "").strip() or len(os.environ.get("CAESAR_ADMIN_PASSWORD", "")) < 12:
    raise RuntimeError("Set CAESAR_ADMIN_EMAIL and a unique CAESAR_ADMIN_PASSWORD (12+ characters) in cPanel.")
if not (ROOT / "dist" / "index.html").is_file():
    raise RuntimeError("Built website missing. Install the complete cPanel ZIP.")

from a2wsgi import ASGIMiddleware
from services.api.main import app, initialize

# Hosting servers may fork workers after importing the startup file. An ASGI
# adapter created here would start a thread that disappears in forked children.
# Build it lazily in the process actually serving the request instead.
_adapter = None
_adapter_pid = None
_adapter_lock = threading.Lock()


def _after_fork():
    global _adapter, _adapter_pid, _adapter_lock
    _adapter = None
    _adapter_pid = None
    _adapter_lock = threading.Lock()


os.register_at_fork(after_in_child=_after_fork)


def application(environ, start_response):
    global _adapter, _adapter_pid
    process = os.getpid()
    if _adapter_pid != process:
        with _adapter_lock:
            if _adapter_pid != process:
                # WSGI does not send ASGI lifespan events. SQLite setup is
                # idempotent; use a new adapter/event loop for each worker.
                initialize()
                _adapter = ASGIMiddleware(app)
                _adapter_pid = process
    return _adapter(environ, start_response)
