"""Prompt for hosted credentials and save them outside public/application files."""

from getpass import getpass
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def configure():
    if "public_html" in ROOT.parts:
        raise SystemExit("Extract the application in your private home directory first.")
    settings = ROOT.parent / ".config" / "caesar" / f"{ROOT.name}.json"
    if settings.exists():
        raise SystemExit(f"Configuration already exists at {settings}; kept unchanged.")
    email = input("Administrator email: ").strip()
    if not email or "@" not in email:
        raise SystemExit("Enter a valid administrator email.")
    password = getpass("New administrator password (12+ characters; hidden): ")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters.")
    if getpass("Confirm password: ") != password:
        raise SystemExit("Passwords do not match; nothing saved.")
    values = {
        "CAESAR_DATA_DIR": str(ROOT.parent / "caesar-data" / ROOT.name),
        "CAESAR_ADMIN_EMAIL": email,
        "CAESAR_ADMIN_PASSWORD": password,
        "CAESAR_LOCAL_DEMO": "0",
        "CAESAR_SECURE_COOKIE": "1",
    }
    settings.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(settings, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        json.dump(values, stream, indent=2)
    print(f"Saved private configuration: {settings}")
    print("No password was printed or passed in command-line arguments.")
    print("This creates the administrator on first startup; it does not reset an existing account.")


if __name__ == "__main__":
    configure()
