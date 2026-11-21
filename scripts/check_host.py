"""Read-only cPanel prerequisite checks. Run inside its Python app environment."""

import argparse
import importlib.util
import platform
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true", help="Check the host before installing dependencies")
    args = parser.parse_args()
    checks = [
        ("Python 3.12", sys.version_info[:2] == (3, 12)),
        ("Linux host", platform.system() == "Linux"),
        ("Unix parser resource limits", importlib.util.find_spec("resource") is not None),
    ]
    try:
        result = subprocess.run([sys.executable, "-c", "print('worker-ok')"], capture_output=True, text=True, timeout=10)
        checks.append(("PDF worker subprocesses", result.returncode == 0 and result.stdout.strip() == "worker-ok"))
    except (OSError, subprocess.TimeoutExpired):
        checks.append(("PDF worker subprocesses", False))
    if not args.preflight:
        for name in ("fastapi", "a2wsgi", "pymupdf", "openpyxl", "multipart"):
            checks.append((f"Installed dependency: {name}", importlib.util.find_spec(name) is not None))
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {platform.python_version()}")
    for label, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'}  {label}")
    print("Passenger command: " + (shutil.which("passenger-config") or "not on PATH; check Setup Python App with your provider"))
    print("Manual checks still required: Python/Passenger account support, HTTPS, private document/data roots, access restrictions, memory and upload limits.")
    return 0 if all(passed for _, passed in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
