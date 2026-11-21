"""Recover the existing CAESAR administrator from its hosting account's shell.

Passwords are prompted privately. Only administrator credentials, that user's
sessions and the account-private bootstrap configuration are changed.
"""

from datetime import datetime, timezone
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile


class RecoveryError(Exception):
    pass


def locations(home):
    home = Path(home).resolve()
    settings = home / ".config/caesar/caesar-system.json"
    if settings.is_symlink() or any(p.is_symlink() for p in settings.parents if p.is_relative_to(home)):
        raise RecoveryError("Private configuration must not use symlinks.")
    if not settings.is_file() or settings.stat().st_mode & 0o077:
        raise RecoveryError("Existing private configuration is required with permissions 600.")
    values = json.loads(settings.read_text())
    value = values.get("CAESAR_DATA_DIR", "")
    data = Path(value).resolve()
    if not Path(value).is_absolute() or not data.is_relative_to(home) or data == home or "public_html" in data.parts or data.is_relative_to(home / "easyai.com.au") or data.is_relative_to(home / "caesar-system"):
        raise RecoveryError("The configured database must be in private account storage.")
    database = data / "workspace.sqlite3"
    if not database.is_file() or database.is_symlink():
        raise RecoveryError("Existing workspace database not found; no database was created.")
    return settings, values, database


def connect(database):
    connection = sqlite3.connect(database.as_uri() + "?mode=rw", uri=True, timeout=20, isolation_level=None)
    connection.row_factory = sqlite3.Row
    return connection


def administrator(connection):
    row = connection.execute("SELECT * FROM users WHERE id=?", ("admin",)).fetchone()
    if not row or row["role"] != "admin":
        raise RecoveryError("The existing bootstrap administrator was not found; no other user was changed.")
    return dict(row)


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return salt + ":" + digest


def private_write(path, content):
    with open(path, "xb", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        stream.write(content)


def replace_configuration(path, content):
    descriptor, temporary = tempfile.mkstemp(prefix=".admin-recovery-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def reset_credentials(home, email, password):
    if not email or "@" not in email or len(email) > 254:
        raise RecoveryError("Enter a valid login email address.")
    if not 12 <= len(password) <= 1024:
        raise RecoveryError("Use a password between 12 and 1024 characters.")
    settings, values, database = locations(home)
    original = settings.read_bytes()
    updated = {**values, "CAESAR_ADMIN_EMAIL": email, "CAESAR_ADMIN_PASSWORD": password}
    new_configuration = (json.dumps(updated, indent=2) + "\n").encode()
    backup_root = settings.parent / "recovery-backups"
    if backup_root.is_symlink():
        raise RecoveryError("Recovery backup directory must not be a symlink.")
    backup_root.mkdir(exist_ok=True, mode=0o700)
    backup_root.chmod(0o700)
    backup = backup_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4))
    backup.mkdir(mode=0o700)
    encoded = password_hash(password)
    connection = connect(database)
    configuration_changed = False
    try:
        connection.execute("BEGIN IMMEDIATE")
        if settings.read_bytes() != original:
            raise RecoveryError("Private configuration changed during recovery; retry after the other operation finishes.")
        old = administrator(connection)
        if connection.execute("SELECT 1 FROM users WHERE email=? AND id<>?", (email, old["id"])).fetchone():
            raise RecoveryError("That email belongs to another existing account; nothing changed.")
        private_write(backup / "configuration.json", original)
        private_write(backup / "administrator.json", json.dumps(old, indent=2).encode())
        connection.execute("UPDATE users SET email=?,password=? WHERE id=? AND role=?", (email, encoded, old["id"], "admin"))
        connection.execute("DELETE FROM sessions WHERE user_id=?", (old["id"],))
        connection.execute("INSERT INTO audit VALUES (?,?,?,?,?,?)", (secrets.token_hex(16), "", old["id"], "Administrator credentials recovered", "Account-owner terminal recovery; administrator sessions revoked", datetime.now(timezone.utc).isoformat()))
        replace_configuration(settings, new_configuration)
        configuration_changed = True
        connection.commit()
    except BaseException:
        connection.rollback()
        if configuration_changed:
            try:
                replace_configuration(settings, original)
            except OSError:
                raise RecoveryError(f"Database transaction rolled back, but private configuration needs restoration from {backup / 'configuration.json'}.") from None
        raise
    finally:
        connection.close()
    return {"email": email, "backup": str(backup)}


def main():
    if not sys.stdin.isatty():
        raise RecoveryError("Run this downloaded file directly in cPanel Terminal; do not pipe it into Python.")
    home = Path.home()
    _, _, database = locations(home)
    connection = connect(database)
    try:
        current = administrator(connection)["email"]
    finally:
        connection.close()
    print("Existing administrator login email:", current)
    email = input("Login email [press Enter to keep it]: ").strip() or current
    password = getpass("Set a NEW password (12+ characters; hidden): ")
    if password != getpass("Confirm the NEW password: "):
        raise RecoveryError("Passwords do not match; nothing changed.")
    result = reset_credentials(home, email, password)
    print("\nAdministrator login updated.")
    print("Website: https://easyai.com.au/stress/")
    print("Login email:", result["email"])
    print("Use the new password you just entered. It has not been printed.")
    print("Previous administrator sessions revoked; projects and drawings retained.")
    print("Private recovery backup:", result["backup"])


if __name__ == "__main__":
    try:
        main()
    except (RecoveryError, OSError, ValueError, sqlite3.Error, KeyboardInterrupt) as exc:
        print("RECOVERY STOPPED: " + (str(exc) if isinstance(exc, RecoveryError) else type(exc).__name__))
        raise SystemExit(1)
