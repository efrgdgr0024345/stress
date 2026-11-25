"""Admin-only release control. Installation runs outside Passenger via cron."""
import fcntl
import hashlib
import io
import json
import os
import re
from pathlib import Path, PurePosixPath
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from urllib.request import Request, urlopen
import zipfile
from services.api import diagnostics as diag

REPO = "efrgdgr0024345/stress"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream)
        os.replace(name, path)
        if path.parent.name=="updates" and path.name in ("state.json","available.json","policy.json","maintenance.json","installed.json"):
            fields={k:v for k,v in value.items() if k in ("status","action","automatic","active","version","commit")}
            diag.emit(path.parent.parent,"update."+path.stem,source="updater",**fields)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def lock(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else (default or {})


def required_security_contract(data):
    """Older code must not bypass MFA, disabled accounts or reviewer roles."""
    data=Path(data)
    minimum=0
    for path in (data/'security/mfa').glob('*.json'):
        if path.is_symlink():raise ValueError('Private account security storage requires operator attention')
        if read(path).get('enabled'):minimum=1
    database=data/'workspace.sqlite3'
    if database.is_file():
        with sqlite3.connect(database) as conn:
            tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'projects' in tables:
                columns={r[1] for r in conn.execute('PRAGMA table_info(projects)')}
                if 'data' in columns:
                    for row in conn.execute('SELECT data FROM projects'):
                        p=json.loads(row[0]);model=p.get('physical_model',{})
                        if (p.get('source_review') or p.get('continuation_source_reviews') or p.get('numbering_history') or model.get('station_constraints') or model.get('retired_station_constraints') or any(n.get('topology_state')=='UNASSIGNED' or n.get('source_observation') or n.get('station_proof') or n.get('manual_station_basis') or n.get('topology_proof') for n in p.get('nodes',[]))
                            or any(m.get('connection_profile') for m in p.get('materials',[]))):minimum=max(minimum,4)
                        if p.get('continuations') or p.get('point_aliases') or any(c.get('cod_derivation') for c in model.get('constraints',[])):minimum=max(minimum,3)
                        if model.get('components') or model.get('constraints') or any(e.get('geometry_origin')=='constraint-solution' for e in p.get('analysis_model',{}).get('elements',[])):minimum=max(minimum,2)
            if 'users' in tables and conn.execute("SELECT 1 FROM users WHERE role='reviewer' LIMIT 1").fetchone():minimum=max(minimum,1)
            if 'account_state' in tables and conn.execute('SELECT 1 FROM account_state WHERE enabled=0 LIMIT 1').fetchone():minimum=max(minimum,1)
            if 'mfa_accounts' in tables and conn.execute('SELECT 1 FROM mfa_accounts WHERE enabled=1 LIMIT 1').fetchone():minimum=max(minimum,1)
            for table in ('review_signoffs','project_approvals','review_qualifications'):
                if table in tables and conn.execute('SELECT 1 FROM '+table+' LIMIT 1').fetchone():minimum=max(minimum,1)
    return minimum


def security_compatible(data,code):
    if read(Path(code)/'RELEASE.json').get('security_contract',0)<required_security_contract(data):
        raise ValueError('That release predates account/review security or model safeguards now in use. Retain this code or use a compatible rollback release.')


@contextmanager
def pipeline_guard(directory):
    """Never replace parser code while a separate pipeline runner is using it."""
    worker=directory.parent/'pipeline';worker.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (worker/'runner.lock').open('a') as stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        database = directory.parent / 'workspace.sqlite3'
        if database.is_file():
            with sqlite3.connect(database, timeout=5) as conn:
                table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='remote_pages'").fetchone()
                if table and conn.execute("SELECT 1 FROM remote_pages WHERE state IN ('SUBMITTING','SUBMITTED','AMBIGUOUS') AND deadline>? LIMIT 1", (time.time(),)).fetchone():
                    # A provider may still be fetching/delivering a page while
                    # the local cron is idle. Keep callback routes available.
                    yield False
                    return
        yield True


def fetch(url, limit=32*1024*1024):
    with urlopen(Request(url, headers={"User-Agent":"CAESAR-updater", "Accept":"application/vnd.github+json"}), timeout=20) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Download exceeds release limit")
    return data


def check(directory):
    commit = json.loads(fetch(f"https://api.github.com/repos/{REPO}/commits/main", 1000000))["sha"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Invalid release commit")
    release = json.loads(fetch(f"https://raw.githubusercontent.com/{REPO}/{commit}/updates/stable.json", 100000))
    if release.get("format") != 1 or release.get("schema") != 2 or release.get("code_only_compatible") is not True or not isinstance(release.get("version"),str) or not re.fullmatch(r"[a-zA-Z0-9._-]{1,40}",release["version"]):
        raise ValueError("Release requires manual migration")
    for name in ("package_sha256", "requirements_sha256"):
        value = release.get(name, "")
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("Invalid release digest")
    release["commit"] = commit
    release["checked_at"] = time.time()
    write(directory / "available.json", release)
    return release


def unpack(data, release, destination):
    if hashlib.sha256(data).hexdigest() != release["package_sha256"]:
        raise ValueError("Release checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if len(archive.infolist()) > 4000 or sum(e.file_size for e in archive.infolist()) > 100*1024*1024:
            raise ValueError("Release expansion exceeds limits")
        seen = set()
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            if not path.parts or path.parts[0] != "caesar-system" or len(path.parts) < 2 or ".." in path.parts or path.is_absolute() or entry.external_attr >> 28 == 0o12:
                raise ValueError("Unsafe release member")
            relative = path.relative_to("caesar-system")
            if relative.as_posix() in seen or any(part in {".env", ".git", ".local", ".venv"} for part in relative.parts):
                raise ValueError("Duplicate or private release member")
            seen.add(relative.as_posix())
            target = destination / str(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
        manifest = read(destination / "MANIFEST.json")["files"]
        if seen != set(manifest) | {"MANIFEST.json"}:
            raise ValueError("Incomplete release manifest")
        for name, digest in manifest.items():
            if hashlib.sha256((destination/name).read_bytes()).hexdigest() != digest:
                raise ValueError("Release file hash mismatch")
    if read(destination / "RELEASE.json").get("version") != release["version"]:
        raise ValueError("Release identity mismatch")


def publish_frontend(root, public, backup=None):
    files = [p for p in (root / "dist").rglob("*") if p.is_file()]
    files += [root/"loader.php", root/"LESSONS_LEARNED.md"]
    records = []
    for source in files:
        relative = source.relative_to(root/"dist") if source.is_relative_to(root/"dist") else Path(source.name)
        target = public / relative
        if target.is_symlink() or not target.resolve().is_relative_to(public.resolve()):
            raise ValueError("Public file escapes the configured directory")
        exists = target.exists()
        if backup and exists:
            saved = backup/relative
            saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(target, saved)
        records.append({"path":str(relative), "existed":exists})
        # Save rollback records before each write, including partial failures.
        if backup:
            write(backup.parent/"public-files.json", records)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o644)


def restore_public(public, backup):
    for record in read(backup/"public-files.json") if (backup/"public-files.json").exists() else []:
        target = public/record["path"]
        if record["existed"]:
            shutil.copyfile(backup/"public"/record["path"], target)
        else:
            target.unlink(missing_ok=True)


def restart(root):
    (root/"tmp").mkdir(exist_ok=True)
    (root/"tmp/restart.txt").touch()
    executable = shutil.which("cloudlinux-selector")
    if executable:
        subprocess.run([executable,"restart","--json","--interpreter","python","--domain","easyai.com.au","--app-root","caesar-system"],capture_output=True,timeout=60)


def healthy(url, version, root):
    for attempt in range(12):
        try:
            result = json.loads(fetch(url.rstrip("/")+"/api/v1/health?update="+secrets.token_hex(6), 100000))
            if result.get("release") == version and result.get("mode") == "authenticated":
                expected=re.findall(rb'assets/[a-zA-Z0-9_.-]+\.js',(root/"dist/index.html").read_bytes())
                page=fetch(url.rstrip("/")+"/?update="+secrets.token_hex(6),1000000)
                if expected and all(asset in page for asset in expected):return True
        except Exception:
            pass
        time.sleep(3)
    return False


def activate(directory, config, release):
    diag.emit(directory.parent,"update.prepare",source="updater",target_release=release["version"])
    root, public = Path(config["app_root"]), Path(config["public_dir"])
    for path in (root, public):
        if path.is_symlink() or not path.is_dir():
            raise ValueError("Configured application/public path is invalid")
    current_hash = hashlib.sha256((root/"requirements.txt").read_bytes()+(root/"requirements-cpanel.txt").read_bytes()).hexdigest()
    if current_hash != release["requirements_sha256"]:
        raise ValueError("Dependency changes require a manual update; current environment retained")
    with tempfile.TemporaryDirectory(prefix="caesar-stage-", dir=root.parent) as temporary:
        stage = Path(temporary)/"caesar-system"
        stage.mkdir(mode=0o711)
        data = fetch(f"https://raw.githubusercontent.com/{REPO}/{release['commit']}/downloads/caesar-cpanel.zip")
        unpack(data, release, stage)
        security_compatible(config['data_dir'],stage)
        diag.emit(directory.parent,"update.package_verified",source="updater",target_release=release["version"],package_bytes=len(data))
        if (stage/"requirements.txt").read_bytes()+(stage/"requirements-cpanel.txt").read_bytes() != (root/"requirements.txt").read_bytes()+(root/"requirements-cpanel.txt").read_bytes():
            raise ValueError("Package dependencies differ")
        settings = read(root.parent/".config/caesar/caesar-system.json")
        environment = {**os.environ, **{k:str(v) for k,v in settings.items() if k.startswith("CAESAR_")}, "CAESAR_DATA_DIR":str(Path(temporary)/"probe-data"), "CAESAR_LOCAL_DEMO":"0"}
        probe = subprocess.run([sys.executable,"-c","from passenger_wsgi import application; import httpx; c=httpx.Client(transport=httpx.WSGITransport(app=application),base_url='https://probe.invalid'); assert c.get('/api/v1/health').json()['mode']=='authenticated'"], cwd=stage, env=environment, capture_output=True, timeout=45)
        if probe.returncode:
            raise ValueError("Staged application startup failed; current release untouched")
        diag.emit(directory.parent,"update.staged_boot_passed",source="updater")
        backup = directory/"backups"/(str(int(time.time()))+"-"+secrets.token_hex(4))
        backup.mkdir(parents=True,mode=0o700)
        with sqlite3.connect(Path(config["data_dir"])/"workspace.sqlite3") as source, sqlite3.connect(backup/"database.sqlite3") as target:
            if source.execute("PRAGMA user_version").fetchone()[0] != release["schema"]:
                raise ValueError("Database schema requires manual migration")
            source.backup(target)
        diag.emit(directory.parent,"update.backup_completed",source="updater")
        write(directory/"maintenance.json", {"active":True})
        write(directory/"journal.json", {"backup":str(backup),"root":str(root),"public":str(public)})
        switched = False
        try:
            os.replace(root, backup/"code")
            try:
                os.replace(stage, root)
            except BaseException:
                os.replace(backup/"code",root)
                raise
            switched = True
            diag.emit(directory.parent,"update.code_activated",source="updater",target_release=release["version"])
            publish_frontend(root, public, backup/"public")
            restart(root)
            if not healthy(config["url"], release["version"], root):
                raise ValueError("New release failed live health checks")
            diag.emit(directory.parent,"update.health_passed",source="updater",target_release=release["version"])
            write(directory/"installed.json", {"version":release["version"],"backup":str(backup),"commit":release["commit"],'package_sha256':release['package_sha256']})
            (directory/"journal.json").unlink(missing_ok=True)
        except BaseException:
            if switched:
                os.replace(root, backup/"failed-code")
                os.replace(backup/"code",root)
                restore_public(public,backup)
                restart(root)
                diag.emit(directory.parent,"update.automatic_rollback_completed","WARNING",source="updater")
            (directory/"journal.json").unlink(missing_ok=True)
            raise
        finally:
            if not (directory/"journal.json").exists():
                (directory/"maintenance.json").unlink(missing_ok=True)


def rollback(directory, config):
    diag.emit(directory.parent,"update.rollback_requested",source="updater")
    installed = read(directory/"installed.json")
    backup = Path(installed.get("backup", ""))
    if not backup.resolve().is_relative_to((directory/"backups").resolve()) or not (backup/"code").is_dir():
        raise ValueError("No retained rollback release")
    root, public = Path(config["app_root"]), Path(config["public_dir"])
    security_compatible(config['data_dir'],backup/'code')
    reverted_version=read(root/'RELEASE.json').get('version')
    write(directory/"maintenance.json", {"active":True})
    write(directory/"journal.json", {"backup":str(backup),"root":str(root),"public":str(public)})
    try:
        os.replace(root,backup/"reverted-code")
        os.replace(backup/"code",root)
        restore_public(public,backup)
        restart(root)
        write(directory/"installed.json", {"version":read(root/"RELEASE.json").get("version","previous")})
        policy=read(directory/'policy.json')
        policy.update(held_package_sha256=installed.get('package_sha256'),held_version=None if installed.get('package_sha256') else reverted_version)
        write(directory/'policy.json',policy)
        (directory/"journal.json").unlink(missing_ok=True)
    finally:
        if not (directory/"journal.json").exists():
            (directory/"maintenance.json").unlink(missing_ok=True)


def run(directory):
    with lock(directory),pipeline_guard(directory) as idle:
        if not idle:
            write(directory/'heartbeat.json',{'at':time.time()})
            diag.emit(directory.parent,'update.waiting_for_pipeline',source='updater')
            return
        config = read(directory/"config.json")
        if not config:
            raise ValueError("Updater is not configured")
        write(directory/"heartbeat.json", {"at":time.time()})
        journal = read(directory/"journal.json")
        if journal:
            backup, root, public = Path(journal["backup"]), Path(journal["root"]), Path(journal["public"])
            if not backup.resolve().is_relative_to((directory/"backups").resolve()) or root != Path(config["app_root"]) or public != Path(config["public_dir"]):
                raise ValueError("Invalid interrupted update journal")
            if (backup/"code").exists():
                if root.exists():os.replace(root,backup/("interrupted-"+secrets.token_hex(4)))
                os.replace(backup/"code",root)
            restore_public(public,backup)
            restart(root)
            write(directory/"installed.json", {"version":read(root/"RELEASE.json").get("version","previous")})
            (directory/"journal.json").unlink()
            (directory/"maintenance.json").unlink(missing_ok=True)
            write(directory/"state.json", {"status":"failed","message":"Interrupted update recovered; previous code restored"})
            return
        state = read(directory/"state.json")
        if state.get("status") == "running":
            # A crashed/terminated attempt is never silently retried.
            write(directory/"state.json", {"status":"interrupted","message":"Previous runner stopped; inspect private backups before retrying"})
            (directory/"maintenance.json").unlink(missing_ok=True)
            return
        action = state.get("action") if state.get("status") == "queued" else None
        if not action and read(directory/"policy.json").get("automatic"):
            release = check(directory)
            policy=read(directory/'policy.json')
            if (release.get('package_sha256') in (state.get('failed_package_sha256'),policy.get('held_package_sha256')) or
                release.get('version')==policy.get('held_version')):
                diag.emit(directory.parent,'update.release_held',source='updater',target_release=release['version'])
                return
            if release["version"] != read(Path(config["app_root"])/"RELEASE.json").get("version"):
                action = "install"
        if not action:
            return
        write(directory/"state.json", {"status":"running","action":action})
        try:
            if action == "rollback": rollback(directory,config)
            else: activate(directory,config,read(directory/"available.json"))
            write(directory/"state.json", {"status":"done","action":action,"at":time.time()})
        except Exception as exc:
            diag.exception(directory.parent,"update.failed",exc,source="updater")
            write(directory/"state.json", {"status":"failed","message":str(exc)[:250],"at":time.time(),
                'failed_package_sha256':read(directory/'available.json').get('package_sha256') if action=='install' else None})


def install(api):
    from fastapi import Depends, HTTPException
    from pydantic import BaseModel
    def admin(actor=Depends(api.user)):
        if actor["role"] != "admin" or (not api.LOCAL_DEMO and actor["id"] != "admin"):
            raise HTTPException(403,"Hosting administrator access required")
        return actor
    @api.app.get("/api/v1/system/updates")
    def status(actor=Depends(admin)):
        directory = api.DATA/"updates"
        backup=read(directory/'installed.json').get('backup');blocked=None
        if backup:
            try:security_compatible(api.DATA,Path(backup)/'code')
            except (ValueError,OSError):blocked='The retained release predates account/review security or model safeguards now in use. A compatible rollback release is required.'
        state=read(directory/'state.json');policy=read(directory/'policy.json')
        hold=bool(state.get('failed_package_sha256') or policy.get('held_package_sha256') or policy.get('held_version'))
        return {"current":api.BUILD_ID,"available":read(directory/"available.json"),"state":state,"configured":(directory/"config.json").exists(),"runner_ready":time.time()-read(directory/"heartbeat.json").get("at",0)<900,"automatic":policy.get("automatic",False),"rollback_available":bool(backup) and not blocked,'rollback_blocked':blocked,'automatic_hold':hold}
    @api.app.post("/api/v1/system/updates/check")
    def check_release(actor=Depends(admin)):
        directory = api.DATA/"updates"
        with lock(directory):
            previous=read(directory/"available.json")
            if time.time()-previous.get("checked_at",0)<60: return previous
            try:return check(directory)
            except Exception:raise HTTPException(502,"GitHub release check failed; installed system retained")
    @api.app.post("/api/v1/system/updates/{action}")
    def queue(action:str, actor=Depends(admin)):
        directory = api.DATA/"updates"
        if action not in ("install","rollback","enable-auto","disable-auto"):raise HTTPException(404)
        with lock(directory):
            if not (directory/"config.json").exists() or time.time()-read(directory/"heartbeat.json").get("at",0)>900:
                raise HTTPException(409,"Enable the cPanel update cron runner first")
            if action.endswith("auto"):
                write(directory/"policy.json", {"automatic":action=="enable-auto"})
            else:
                if read(directory/"state.json").get("status") in ("queued","running","interrupted"): raise HTTPException(409,"Update already queued/running or requires recovery")
                if action=="install" and not read(directory/"available.json").get("commit"):raise HTTPException(409,"Check for a release first")
                write(directory/"state.json", {"status":"queued","action":action,"actor":actor["id"]})
        return {"ok":True}
