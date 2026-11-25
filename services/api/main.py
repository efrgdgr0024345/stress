"""Local-first engineering review API. Production infrastructure is documented separately."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from copy import deepcopy
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from packages.engineering import compute_reasons, dimension_mm, renumber, validate, topology_assigned, source_location_reviewed, refresh_source_locations, source_observations, record_source_location_review
from packages.pdf import create_sample, export_bundle
from services.api import diagnostics as diag

ROOT = Path(__file__).resolve().parents[2]
BUILD_ID = json.loads((ROOT / "RELEASE.json").read_text())["version"] if (ROOT / "RELEASE.json").exists() else "0.2.0"
DATA = Path(os.environ.get("CAESAR_DATA_DIR", ROOT / ".local"))
LOCAL_DEMO = os.environ.get("CAESAR_LOCAL_DEMO", "1") == "1"
LOCK = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid4())


def db():
    conn = sqlite3.connect(DATA / "workspace.sqlite3", timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def audit(conn, project, actor, action, detail=""):
    conn.execute(
        "INSERT INTO audit VALUES (?,?,?,?,?,?)",
        (uid(), project, actor, action, detail, now()),
    )


def initialize():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("sources", "exports", "catalogs"):
        (DATA / name).mkdir(exist_ok=True, mode=0o700)
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT, tenant TEXT);
        CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires INTEGER);
        CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, version INTEGER, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS revisions (id TEXT, version INTEGER, data TEXT, PRIMARY KEY(id,version));
        CREATE TABLE IF NOT EXISTS audit (id TEXT PRIMARY KEY, project_id TEXT, actor TEXT, action TEXT, detail TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, project_id TEXT, filename TEXT, sha256 TEXT);
        CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, project_id TEXT, revision INTEGER, filename TEXT, created TEXT, count INTEGER);
        CREATE TABLE IF NOT EXISTS catalogs (id TEXT PRIMARY KEY, tenant TEXT, filename TEXT, sha256 TEXT, created TEXT, data TEXT);
        CREATE TABLE IF NOT EXISTS catalog_versions (id TEXT PRIMARY KEY, tenant TEXT, catalog_id TEXT, seq INTEGER, created TEXT, data TEXT, UNIQUE(catalog_id,seq));
        PRAGMA user_version=2;
        """)
        from services.api.pipeline import schema as pipeline_schema
        pipeline_schema(conn)
        from services.api.account_security import schema as security_schema
        security_schema(conn)
        from services.api.review_flow import schema as review_schema
        review_schema(conn)
        if LOCAL_DEMO:
            conn.execute(
                "INSERT OR IGNORE INTO users VALUES (?,?,?,?,?,?)",
                (
                    "local-engineer",
                    "Alex Morgan",
                    "engineer@local",
                    "",
                    "admin",
                    "local",
                ),
            )
            if not conn.execute(
                "SELECT 1 FROM projects WHERE tenant=?", ("local",)
            ).fetchone():
                seed(conn)
        elif os.environ.get("CAESAR_ADMIN_PASSWORD"):
            password = os.environ["CAESAR_ADMIN_PASSWORD"]
            if len(password) < 12:
                raise RuntimeError(
                    "CAESAR_ADMIN_PASSWORD must be at least 12 characters."
                )
            conn.execute(
                "INSERT OR IGNORE INTO users VALUES (?,?,?,?,?,?)",
                (
                    "admin",
                    "Administrator",
                    os.environ.get("CAESAR_ADMIN_EMAIL", "admin@local"),
                    password_hash(password),
                    "admin",
                    "default",
                ),
            )
    diag.emit(DATA,"worker.ready",release_id=BUILD_ID,mode="local-development" if LOCAL_DEMO else "authenticated")


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt.encode(), n=16384, r=8, p=1
    ).hex()
    return f"{salt}:{digest}"


def empty_project(title, line, description=""):
    return {
        "id": uid(),
        "title": title,
        "line_id": line,
        "description": description,
        "version": 1,
        "status": "DRAFT",
        "created": now(),
        "updated": now(),
        "sample": False,
        "sheets": [],
        "nodes": [],
        "materials": [],
        "materials_reviewed": False,
        "layout_reviewed": False,
        "numbering_map": [],
    }


def seed(conn):
    project = empty_project(
        "North utility corridor",
        "DEMO-8-CS-001",
        "A two-sheet, synthetic isometric for exploring the review workflow.",
    )
    project["sample"] = True
    project["status"] = "ENGINEERING_REVIEW"
    source_id = uid()
    path = DATA / "sources" / f"{source_id}.pdf"
    create_sample(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    conn.execute(
        "INSERT INTO sources VALUES (?,?,?,?)",
        (source_id, project["id"], "training-isometric.pdf", sha),
    )
    for index in range(2):
        project["sheets"].append(
            {
                "id": uid(),
                "source_id": source_id,
                "filename": "training-isometric.pdf",
                "sha256": sha,
                "page_index": index,
                "width": 1100,
                "height": 760,
                "rotation": 0,
                "printed_id": f"ISO-TRAINING-001 / {index + 1}",
                "line_id": project["line_id"],
                "format": "Vector / text",
                "text": "Synthetic training fixture. Not the original 1010.",
                "axis": [110, 130],
                "table": [710, 370] if index == 0 else [55, 210],
            }
        )
    positions = [
        [
            (160, 485),
            (255, 430),
            (340, 381),
            (425, 430),
            (500, 473),
            (500, 370),
            (500, 282),
            (600, 224),
            (710, 161),
            (800, 213),
            (885, 262),
        ],
        [
            (170, 485),
            (260, 433),
            (350, 381),
            (445, 435),
            (540, 490),
            (635, 435),
            (730, 380),
            (730, 295),
            (730, 210),
            (825, 155),
            (920, 100),
        ],
    ]
    for sheet_index, coords in enumerate(positions):
        for index, (x, y) in enumerate(coords):
            if sheet_index == 1 and index == 0:
                project["nodes"][-1]["instances"].append(
                    {
                        "sheet_id": project["sheets"][1]["id"],
                        "anchor": [x, y],
                        "bubble": [x - 30, y - 30],
                    }
                )
                continue
            order = sheet_index * 10 + index
            kind = (
                "continuation"
                if sheet_index == 0 and index == 10
                else (
                    "support"
                    if index in (2, 3)
                    else (
                        "tee"
                        if index == 4
                        else (
                            "elbow"
                            if index == 6
                            else "endpoint" if index in (0, 10) else "flange"
                        )
                    )
                )
            )
            known = index not in (4, 7)
            station = order * 600 if index != 3 else (sheet_index * 10 + 2) * 600 + 50.8
            project["nodes"].append(
                {
                    "id": uid(),
                    "line_id": project["line_id"],
                    "route": "main",
                    "order": order,
                    "kind": kind,
                    "station_mm": str(station) if known else None,
                    "evidence": (
                        "Synthetic training dimension; not real engineering evidence."
                        if known
                        else ""
                    ),
                    "number": None,
                    "instances": [
                        {
                            "sheet_id": project["sheets"][sheet_index]["id"],
                            "anchor": [x, y],
                            "bubble": [x - 28, y - 32],
                        }
                    ],
                }
            )
    sheet = project["sheets"][0]
    for index, (x, y) in enumerate([(570, 513), (646, 557), (646, 588)]):
        project["nodes"].append(
            {
                "id": uid(),
                "line_id": project["line_id"],
                "route": "branch-01",
                "takeoff_id": project["nodes"][4]["id"],
                "order": index,
                "kind": "endpoint" if index == 2 else "support",
                "station_mm": None,
                "evidence": "",
                "number": None,
                "instances": [
                    {
                        "sheet_id": sheet["id"],
                        "anchor": [x, y],
                        "bubble": [x + 30, y - 30],
                    }
                ],
            }
        )
    for sheet in project["sheets"]:
        for i, family in enumerate(["pipe", "elbow", "flange", "valve"]):
            project["materials"].append(
                {
                    "id": uid(),
                    "sheet_id": sheet["id"],
                    "item_no": str(i + 1),
                    "family": family,
                    "description": [
                        "Pipe, seamless, ASTM A106 Gr B",
                        "Elbow, 90°, ASTM A234 WPB",
                        "Weld neck flange, ASME B16.5",
                        "Ball valve, vendor unconfirmed",
                    ][i],
                    "size": "8 in",
                    "quantity": [1, 2, 2, 1][i],
                    "observed": [1, 2, 2, 0][i],
                    "evidence": "Synthetic source materials list; needs engineer review.",
                }
            )
    project["numbering_map"] = renumber(project["nodes"])
    compute_reasons(project["nodes"])
    conn.execute(
        "INSERT INTO projects VALUES (?,?,?,?)",
        (project["id"], "local", 1, json.dumps(project)),
    )
    conn.execute(
        "INSERT INTO revisions VALUES (?,?,?)", (project["id"], 1, json.dumps(project))
    )
    audit(conn, project["id"], "System", "Created synthetic training project")


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="CAESAR ISO Engineering API", version="0.2.0", lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def safe_validation_error(request, error):
    return JSONResponse(status_code=422,content={'detail':[
        {key:item[key] for key in ('loc','msg','type') if key in item}
        for item in error.errors()[:30]]})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    mount=request.scope.get('root_path','').rstrip('/')
    path=request.url.path.removeprefix(mount)
    public_probe=request.method in ('GET','HEAD') and (path in ('/','/index.html') or path.startswith('/assets/'))
    if (DATA / "updates/maintenance.json").exists() and not public_probe and request.url.path.endswith("/api/v1/health") is False and "/api/v1/system/updates" not in request.url.path:
        return Response("System update in progress. Please retry shortly.", status_code=503, headers={"Retry-After":"30"})
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlsplit

            if urlsplit(origin).netloc != request.headers.get("host") or urlsplit(origin).scheme != request.url.scheme:
                return Response(
                    "Cross-origin writes are not permitted.", status_code=403
                )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


def user(request: Request):
    import time

    token = request.cookies.get("caesar_session", "")
    digest = hashlib.sha256(token.encode()).hexdigest()
    with db() as conn:
        row = conn.execute(
            "SELECT users.* FROM users JOIN sessions ON users.id=sessions.user_id WHERE sessions.token=? AND sessions.expires>?",
            (digest, int(time.time())),
        ).fetchone()
    if not row or (not LOCAL_DEMO and row["id"] == "local-engineer"):
        raise HTTPException(401, "Sign in to your workspace.")
    from services.api.account_security import active as active_account
    with db() as conn:
        if not active_account(conn,row['id']):raise HTTPException(401,'Sign in to your workspace.')
    diag.bind_actor(dict(row))
    return dict(row)


def editor(actor=Depends(user)):
    if actor["role"] not in ('admin','engineer'):
        raise HTTPException(403, "Engineering editor permission required.")
    return actor


def project_read(project_id, actor, conn):
    row = conn.execute(
        "SELECT * FROM projects WHERE id=? AND tenant=?", (project_id, actor["tenant"])
    ).fetchone()
    if not row:
        raise HTTPException(404, "Project not found.")
    return json.loads(row["data"])


def change(project_id, version, actor, action, update):
    diag.emit(DATA,"project.change.started","DEBUG",base_revision=version)
    with LOCK, db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if (DATA/'updates/maintenance.json').exists():raise HTTPException(503,'Workspace maintenance is running. Retry shortly.')
        who=conn.execute('SELECT role FROM users WHERE id=? AND tenant=?',(actor['id'],actor['tenant'])).fetchone()
        from services.api.account_security import active
        if not who or who['role'] not in ('admin','engineer') or not active(conn,actor['id']):
            raise HTTPException(403,'Engineering editor access changed. Sign in again.')
        project = project_read(project_id, actor, conn)
        if project["version"] != version:
            raise HTTPException(
                409, "This project changed in another session. Reload before saving."
            )
        update(project)
        refresh_source_locations(project)
        from packages.physical import prepare as prepare_physical
        prepare_physical(project)
        from packages.engineering.continuations import apply_reasons
        apply_reasons(project)
        from packages.physical.constraints import apply_geometry_reasons
        apply_geometry_reasons(project)
        from packages.physical.stations import apply_station_reasons
        apply_station_reasons(project)
        from packages.physical.source_exceptions import refresh_source_exceptions
        refresh_source_exceptions(project)
        project['contributors'] = sorted(set(project.get('contributors', [])) | {actor['id']})
        compute_reasons(project["nodes"])
        project["version"] += 1
        project["updated"] = now()
        if action != "Submitted for engineering review":
            project["status"] = "DRAFT"
            project.pop("review_approval", None)
        conn.execute(
            "UPDATE projects SET version=?,data=? WHERE id=?",
            (project["version"], json.dumps(project), project_id),
        )
        conn.execute(
            "INSERT INTO revisions VALUES (?,?,?)",
            (project_id, project["version"], json.dumps(project)),
        )
        audit(conn, project_id, actor["name"], action)
        if project.get("automation",{}).get("run_id"):
            conn.execute("INSERT OR IGNORE INTO pipeline_outbox VALUES (?,?,?,?)",(project_id,project["version"],actor["id"],time.time()))
    project["issues"] = validate(project)
    diag.emit(DATA,"project.change.completed",revision=project["version"],sheets=len(project["sheets"]),nodes=len(project["nodes"]),materials=len(project["materials"]),issues=len(project["issues"]))
    return project


def session(response, actor, request):
    diag.bind_actor(actor)
    import time

    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                actor["id"],
                int(time.time()) + 43200,
            ),
        )
        from services.api.account_security import bind as bind_assurance
        bind_assurance(conn,hashlib.sha256(token.encode()).hexdigest(),actor['id'],actor.get('_mfa_verified',False))
    response.set_cookie(
        "caesar_session",
        token,
        httponly=True,
        samesite="strict",
        secure=os.environ.get("CAESAR_SECURE_COOKIE", "0") == "1",
        max_age=43200,
        path=request.scope.get("root_path", "").rstrip("/") + "/",
    )
    diag.emit(DATA,"security.login_succeeded")
    return {k: actor[k] for k in ("id", "name", "email", "role")}


@app.get("/api/v1/health")
def health():
    return {
        "status": "ok",
        "mode": "local-development" if LOCAL_DEMO else "authenticated",
        "version": "0.2.0",
        "release": BUILD_ID,
    }


@app.get("/api/v1/auth/me")
def me(actor=Depends(user)):
    return {k: actor[k] for k in ("id", "name", "email", "role")}


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)
    code: str | None = Field(default=None,max_length=80)


@app.post("/api/v1/auth/local")
def local_login(response: Response, request: Request):
    if not LOCAL_DEMO:
        raise HTTPException(403, "Local demo access is disabled.")
    with db() as conn:
        actor = dict(
            conn.execute(
                "SELECT * FROM users WHERE id=?", ("local-engineer",)
            ).fetchone()
        )
    return session(response, actor, request)


@app.post("/api/v1/auth/login")
def login(body: Login, response: Response, request: Request):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE lower(email)=?", (body.email.strip().casefold(),)
        ).fetchone()
        from services.api.account_security import active as active_account
        enabled=bool(row and active_account(conn,row['id']))
    if (
        not row
        or not enabled
        or not row["password"]
        or not secrets.compare_digest(
            password_hash(body.password, row["password"].split(":")[0]), row["password"]
        )
    ):
        diag.emit(DATA,"security.login_failed","WARNING",reason="credentials_rejected")
        raise HTTPException(401, "Email or password is incorrect.")
    actor=dict(row)
    from services.api.account_security import status as security_status, verify as verify_factor
    if security_status(sys.modules[__name__],actor)['enabled']:
        if not body.code:raise HTTPException(401,'Enter your authenticator or recovery code.')
        verify_factor(sys.modules[__name__],actor,body.code)
        actor['_mfa_verified']=True
    return session(response, actor, request)


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response):
    with db() as conn:
        conn.execute('DELETE FROM session_assurance WHERE session_hash=?', (hashlib.sha256(request.cookies.get('caesar_session', '').encode()).hexdigest(),))
        conn.execute(
            "DELETE FROM sessions WHERE token=?",
            (
                hashlib.sha256(
                    request.cookies.get("caesar_session", "").encode()
                ).hexdigest(),
            ),
        )
    response.delete_cookie("caesar_session", path=request.scope.get("root_path", "").rstrip("/") + "/")
    return {"ok": True}


@app.get("/api/v1/projects")
def projects(actor=Depends(user)):
    with db() as conn:
        values = [
            json.loads(r["data"])
            for r in conn.execute(
                "SELECT data FROM projects WHERE tenant=? ORDER BY rowid DESC",
                (actor["tenant"],),
            )
        ]
    return [{**p, "issues": validate(p)} for p in values]


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    line_id: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=2000)


@app.post("/api/v1/projects", status_code=201)
def create_project(body: ProjectCreate, actor=Depends(editor)):
    if not body.title.strip() or not body.line_id.strip():
        raise HTTPException(422, "Project name and full line ID are required.")
    project = empty_project(body.title.strip(), body.line_id.strip(), body.description)
    with db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if (DATA/'updates/maintenance.json').exists():raise HTTPException(503,'Workspace maintenance is running. Retry shortly.')
        conn.execute(
            "INSERT INTO projects VALUES (?,?,?,?)",
            (project["id"], actor["tenant"], 1, json.dumps(project)),
        )
        conn.execute(
            "INSERT INTO revisions VALUES (?,?,?)",
            (project["id"], 1, json.dumps(project)),
        )
        audit(conn, project["id"], actor["name"], "Created project")
    project["issues"] = validate(project)
    return project


@app.get("/api/v1/projects/{project_id}")
def get_project(project_id: str, actor=Depends(user)):
    with db() as conn:
        project = project_read(project_id, actor, conn)
    project["issues"] = validate(project)
    return project


@app.get("/api/v1/projects/{project_id}/graph")
def graph(project_id: str, actor=Depends(user)):
    return get_project(project_id, actor)["graph"]


@app.get("/api/v1/projects/{project_id}/validation")
def validation(project_id: str, actor=Depends(user)):
    return get_project(project_id, actor)["issues"]


@app.post("/api/v1/projects/{project_id}/sources")
async def upload(
    project_id: str, version: int, file: UploadFile = File(...), actor=Depends(editor)
):
    diag.emit(DATA,"pdf.upload.received","DEBUG")
    with db() as conn:
        project_read(project_id, actor, conn)
    if Path(file.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(
            415, "Upload a PDF file. ZIP import is not supported in this MVP."
        )
    source_id = uid()
    path = DATA / "sources" / f"{source_id}.pdf"
    size = 0
    digest = hashlib.sha256()
    try:
        with path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 30 * 1024 * 1024:
                    raise HTTPException(413, "PDF exceeds the 30 MB limit.")
                digest.update(chunk)
                out.write(chunk)
        with path.open("rb") as inp:
            if inp.read(5) != b"%PDF-":
                raise HTTPException(415, "The file signature is not a PDF.")
        diag.emit(DATA,"pdf.parse.started","DEBUG",source_id=source_id,input_bytes=size)
        parser_started=time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-m", "services.api.pdf_worker", str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=25,
        )
        if result.returncode:
            diag.emit(DATA,"pdf.parse.rejected","WARNING",source_id=source_id,exit_code=result.returncode,duration_ms=round((time.perf_counter()-parser_started)*1000,2))
            raise HTTPException(
                422,
                "PDF rejected: invalid, encrypted, active content, or parser resource limit. Use a plain PDF.",
            )
        pages = json.loads(result.stdout)
        sha = digest.hexdigest()
        diag.emit(DATA,"pdf.parse.completed",source_id=source_id,pages=len(pages),input_bytes=size,sha256=sha,duration_ms=round((time.perf_counter()-parser_started)*1000,2))
        filename = Path(file.filename or "source.pdf").name[:200]

        def update(p):
            if sha in {s["sha256"] for s in p["sheets"]}:
                raise HTTPException(409, "This exact source PDF is already registered.")
            if len(p["sheets"]) + len(pages) > 200:
                raise HTTPException(422, "A project supports up to 200 pages.")
            for page in pages:
                p["sheets"].append(
                    {
                        **page,
                        "id": uid(),
                        "source_id": source_id,
                        "filename": filename,
                        "sha256": sha,
                        "printed_id": "",
                        "line_id": p["line_id"],
                        "axis": None,
                        "table": None,
                    }
                )
            p["layout_reviewed"] = False
            p["materials_reviewed"] = False

        with LOCK:
            # Source metadata is scoped by project before it can be downloaded.
            with db() as conn:
                if (DATA/'updates/maintenance.json').exists():raise HTTPException(503,'Workspace maintenance is running. Retry shortly.')
                conn.execute(
                    "INSERT INTO sources VALUES (?,?,?,?)",
                    (source_id, project_id, filename, sha),
                )
            try:
                return change(
                    project_id,
                    version,
                    actor,
                    f"Registered {len(pages)} PDF pages",
                    update,
                )
            except Exception:
                with db() as conn:
                    conn.execute("DELETE FROM sources WHERE id=?", (source_id,))
                raise
    except subprocess.TimeoutExpired:
        diag.emit(DATA,"pdf.parse.timeout","ERROR",source_id=source_id,timeout_seconds=25)
        path.unlink(missing_ok=True)
        raise HTTPException(
            422, "PDF parser timed out. Split the drawing into smaller sources."
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise


@app.get("/api/v1/projects/{project_id}/sources/{source_id}")
def source_file(project_id: str, source_id: str, actor=Depends(user)):
    with db() as conn:
        project = project_read(project_id, actor, conn)
        row = conn.execute(
            "SELECT * FROM sources WHERE id=? AND project_id=?", (source_id, project_id)
        ).fetchone()
    permitted={s["source_id"] for s in project["sheets"]}|{s["source_id"] for s in project.get("source_history",[])}
    if not row or source_id not in permitted:
        raise HTTPException(404, "Source not found.")
    return FileResponse(
        DATA / "sources" / f"{source_id}.pdf",
        media_type="application/pdf",
        filename=row["filename"],
    )


class Version(BaseModel):
    version: int = Field(ge=1)


class SheetPatch(Version):
    printed_id: str = Field(max_length=150)
    line_id: str = Field(min_length=1, max_length=150)
    axis: tuple[float, float] | None = None
    table: tuple[float, float] | None = None
    confirm_identity:bool=False


def sheet_for(project, sheet_id):
    sheet = next((s for s in project["sheets"] if s["id"] == sheet_id), None)
    if not sheet:
        raise HTTPException(404, "Sheet not found.")
    return sheet


@app.patch("/api/v1/projects/{project_id}/sheets/{sheet_id}")
def patch_sheet(
    project_id: str, sheet_id: str, body: SheetPatch, actor=Depends(editor)
):
    def update(p):
        sheet = sheet_for(p, sheet_id)
        if body.confirm_identity and (not body.printed_id.strip() or not body.line_id.strip()):raise HTTPException(422,"Confirm the printed sheet identity and full line ID before marking the register reviewed.")
        for key in ("axis", "table"):
            point = getattr(body, key)
            if point and not (
                50 <= point[0] <= sheet["width"] - 60
                and 50 <= point[1] <= sheet["height"] - 110
            ):
                raise HTTPException(
                    422,
                    "Place the annotation inside the page with at least 50 pt clearance.",
                )
        identity_changed=sheet.get('printed_id')!=body.printed_id or sheet.get('line_id')!=body.line_id
        sheet.update(body.model_dump(exclude={"version","confirm_identity"}))
        if body.confirm_identity:sheet["identity_verified"]=True
        elif identity_changed:sheet['identity_verified']=False
        p["layout_reviewed"] = False

    return change(
        project_id, body.version, actor, "Updated sheet register / layout", update
    )


class Instance(BaseModel):
    sheet_id: str
    anchor: tuple[float, float]
    bubble: tuple[float, float]


class NodeInput(Version):
    model_config = ConfigDict(extra="forbid")
    line_id: str = Field(min_length=1, max_length=150)
    route: str | None = Field(default=None, pattern=r"^(main|branch-\d{2})$")
    takeoff_id: str | None = None
    order: int | None = Field(default=None, ge=0, le=100000)
    topology_state: Literal['ASSIGNED','UNASSIGNED'] = 'ASSIGNED'
    topology_confirmed: bool = False
    source_location_confirmed: bool = False
    source_location_sheet_id: str | None = Field(default=None,max_length=100)
    kind: str = Field(
        pattern=r"^(endpoint|flange|tee|elbow|support|valve|instrument|continuation)$"
    )
    dimension: str = Field(default="", max_length=100)
    evidence: str = Field(default="", max_length=3000)
    source_feature_id: str | None = Field(default=None,pattern=r'^[a-f0-9-]{36}$')
    source_feature_role: str | None = Field(default=None,pattern=r'^(flange_face|opposite_pipe_dot)$')
    instances: list[Instance] = Field(min_length=1, max_length=200)


def apply_node(project, body, node_id=None, actor=None):
    node = (
        next((n for n in project["nodes"] if n["id"] == node_id), None)
        if node_id
        else None
    )
    if node_id and not node:
        raise HTTPException(404, "Physical point not found.")
    sheets = {s['id']: s for s in project['sheets']}
    observations = source_observations(node) if node else []
    observation = next((o for o in observations if o.get('sheet_id')==body.source_location_sheet_id),None) if body.source_location_sheet_id else (observations[0] if observations else None)
    location_preview = deepcopy(node) if node else None
    if location_preview is not None:location_preview['instances']=[i.model_dump() for i in body.instances]
    if observations and set(i.sheet_id for i in body.instances)-{i['sheet_id'] for i in node['instances']}:
        raise HTTPException(422,'Use continuation review with independent source proof to add another depiction of this source point.')
    topology_state = body.topology_state
    if node and not topology_assigned(node) and 'topology_state' not in body.model_fields_set and not body.topology_confirmed:
        topology_state = 'UNASSIGNED'
    if topology_state == 'UNASSIGNED':
        if body.route is not None or body.order is not None or body.takeoff_id:
            raise HTTPException(422, 'Unassigned source points have no route/order/takeoff. Explicitly confirm topology before assigning an engineering route.')
    else:
        if body.route is None or body.order is None:
            raise HTTPException(422, 'An assigned model point needs an explicit route and physical sequence order.')
        if node and not topology_assigned(node) and not body.topology_confirmed:
            raise HTTPException(422, 'Explicit topology confirmation is required before promoting an unassigned source point into the ordered model.')
        if observations and not body.source_location_confirmed and not source_location_reviewed(location_preview, sheets):
            raise HTTPException(422, 'Review the actual source location separately before accepting this source point into an ordered route.')
    source_review_proof = None
    if body.source_location_confirmed:
        if not observation or not actor:
            raise HTTPException(422, 'Source-location confirmation requires an existing source observation and an authorised reviewer.')
        sheet = sheets.get(observation.get('sheet_id'))
        current = bool(sheet and (observation.get('content_hash') == sheet.get('content_hash')
            if observation.get('content_hash') else observation.get('source_sha256') == sheet.get('sha256')))
        instance = next((i for i in body.instances if sheet and i.sheet_id == sheet['id']), None)
        if not current or not instance:
            raise HTTPException(409, 'The original source observation changed or is no longer depicted. Refresh its source evidence before confirming a location.')
        if len(body.evidence.strip()) < 10:
            raise HTTPException(422, 'Describe the source feature and location evidence before confirming its inspection.')
        source_review_proof = {'sheet_id': sheet['id'], 'source_sha256': sheet['sha256'],
            'content_hash': sheet.get('content_hash'), 'anchor': list(instance.anchor),
            'evidence': body.evidence, 'reviewed_by': actor['id'], 'reviewed_at': now()}
    if source_review_proof and topology_state=='ASSIGNED' and node and not topology_assigned(node):
        record_source_location_review(location_preview,source_review_proof)
        if not source_location_reviewed(location_preview,sheets):
            raise HTTPException(422,'Review every source depiction independently before promoting this shared point into an ordered route.')
    if bool(body.source_feature_id)!=bool(body.source_feature_role):
        raise HTTPException(422,'A source feature needs both its identity and interface role.')
    if body.source_feature_id:
        reference=(body.source_feature_id,body.source_feature_role)
        if any(((n.get('source_feature_id'),n.get('source_feature_role'))==reference or
                any((v['id'],v['role'])==reference for v in n.get('source_feature_links',[]))) and n['id']!=node_id for n in project['nodes']):
            raise HTTPException(409,'This source interface already has a physical point. Select its existing identity.')
        retained=bool(node and (node.get('source_feature_id'),node.get('source_feature_role'))==reference)
        if not retained:
            feature=next((f for f in project.get('automation',{}).get('feature_proposals',[]) if f['id']==body.source_feature_id),None)
            if not feature or not any(i.sheet_id==feature['sheet_id'] and list(i.anchor)==feature[body.source_feature_role] for i in body.instances):
                raise HTTPException(422,'A new source association must use the current detected interface on its actual source page.')
    if body.takeoff_id:
        tee = next((n for n in project["nodes"] if n["id"] == body.takeoff_id), None)
        if (
            body.route == "main"
            or not tee
            or tee["kind"] != "tee"
            or tee["route"] != "main"
            or tee["line_id"] != body.line_id
            or not topology_assigned(tee)
        ):
            raise HTTPException(
                422, "Branch takeoff must be an existing main-run tee on the same line."
            )
    if (
        node
        and node["kind"] == "tee"
        and any(n.get("takeoff_id") == node_id for n in project["nodes"])
    ):
        if (
            body.kind != "tee"
            or body.route != "main"
            or body.line_id != node["line_id"]
        ):
            raise HTTPException(
                422, "Reassign dependent branches before changing this tee identity."
            )
    seen = set()
    for inst in body.instances:
        sheet = sheet_for(project, inst.sheet_id)
        if inst.sheet_id in seen:
            raise HTTPException(422, "A point can appear only once on each sheet.")
        seen.add(inst.sheet_id)
        for x, y in (inst.anchor, inst.bubble):
            if not (12 <= x <= sheet["width"] - 12 and 12 <= y <= sheet["height"] - 12):
                raise HTTPException(
                    422, "Keep anchors and bubbles inside the PDF page."
                )
    try:
        station = str(dimension_mm(body.dimension)) if body.dimension.strip() else None
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if station is not None and not body.evidence.strip():
        raise HTTPException(
            422, "Physical stations require a dimension source / engineering evidence."
        )
    data = {
        **body.model_dump(exclude={"version", "dimension", "topology_confirmed", "source_location_confirmed", "source_location_sheet_id"}),
        'topology_state': topology_state,
        "station_mm": station,
        "dimension_input": body.dimension,
    }
    if node and not {'source_feature_id','source_feature_role'} & body.model_fields_set:
        data.update({key:node.get(key) for key in ('source_feature_id','source_feature_role')})
    if node:
        from packages.physical.stations import manual_station_override
        manual_station_override(node, station)
        node.update(data)
        if topology_state == 'ASSIGNED':
            node["verification"]="reviewed"
        else:
            node.setdefault('verification', 'proposed')
    else:
        point_id = uid()
        project["nodes"].append({**data, "id": point_id, "number": None,
            'review_label': 'P-'+point_id[:8],
            "verification":"reviewed" if topology_state == 'ASSIGNED' else 'proposed'})
    if topology_state == 'UNASSIGNED':
        target = node or project['nodes'][-1]
        target.update(route=None, order=None, takeoff_id=None, number=None)
        target.setdefault('review_label', 'P-'+target['id'][:8])
    if source_review_proof:
        target = node or project['nodes'][-1]
        record_source_location_review(target,source_review_proof)
    if topology_state == 'ASSIGNED' and body.route != "main":
        for member in project["nodes"]:
            if member["line_id"] == body.line_id and member["route"] == body.route:
                member["takeoff_id"] = body.takeoff_id
    try:
        project["numbering_map"] = renumber(project["nodes"])
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    project["layout_reviewed"] = False


@app.post("/api/v1/projects/{project_id}/nodes")
def add_node(project_id: str, body: NodeInput, actor=Depends(editor)):
    return change(
        project_id,
        body.version,
        actor,
        "Added physical point",
        lambda p: apply_node(p, body, actor=actor),
    )


@app.patch("/api/v1/projects/{project_id}/nodes/{node_id}")
def patch_node(project_id: str, node_id: str, body: NodeInput, actor=Depends(editor)):
    return change(
        project_id,
        body.version,
        actor,
        "Updated physical point / presentation",
        lambda p: apply_node(p, body, node_id, actor=actor),
    )


@app.delete("/api/v1/projects/{project_id}/nodes/{node_id}")
def delete_node(project_id: str, node_id: str, version: int, actor=Depends(editor)):
    def update(p):
        if not any(n["id"] == node_id for n in p["nodes"]):
            raise HTTPException(404, "Point not found.")
        p.setdefault("automation_tombstones",{}).setdefault("node_ids",[]).append(node_id)
        if any(n.get("takeoff_id") == node_id for n in p["nodes"]):
            raise HTTPException(
                422, "Reassign dependent branches before deleting their shared tee."
            )
        p["nodes"] = [n for n in p["nodes"] if n["id"] != node_id]
        try:
            p["numbering_map"] = renumber(p["nodes"])
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        p["layout_reviewed"] = False

    return change(project_id, version, actor, "Deleted physical point", update)


@app.post("/api/v1/projects/{project_id}/nodes/renumber")
def renumber_nodes(project_id: str, body: Version, actor=Depends(editor)):
    def update(p):
        try:
            p["numbering_map"] = renumber(p["nodes"])
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    return change(
        project_id, body.version, actor, "Renumbered routes deterministically", update
    )


class MaterialInput(Version):
    sheet_id: str
    item_no: str = Field(min_length=1, max_length=50)
    family: str = Field(
        pattern=r"^(pipe|elbow|tee|support|flange|valve|instrument|other)$"
    )
    description: str = Field(min_length=1, max_length=1000)
    size: str = Field(max_length=100)
    quantity: int | None = Field(default=None, ge=0, le=100000)
    observed: int = Field(ge=0, le=100000)
    evidence: str = Field(default="", max_length=3000)
    quantity_value:str|None=Field(default=None,max_length=100)
    quantity_unit:str=Field(default="count",pattern=r"^(count|m|mm|ft|in|unresolved)$")
    observed_quantity_value:str|None=Field(default=None,max_length=100)


def material_values(body):
    from decimal import Decimal,InvalidOperation
    data=body.model_dump(exclude={"version"})
    for key in ('quantity_value','observed_quantity_value'):
        value=data[key]
        if value is None or not value.strip():data[key]=None;continue
        try:number=Decimal(value)
        except InvalidOperation:raise HTTPException(422,"Source and reconciled quantities must be numeric values in the selected unit.")
        if not number.is_finite() or not 0<=number<=Decimal('1000000000'):raise HTTPException(422,"Quantity must be finite and nonnegative.")
        data[key]=str(number)
    if data['quantity_unit']=='count':
        if data['quantity_value'] is None and data['quantity'] is not None:data['quantity_value']=str(data['quantity'])
        if data['quantity_value'] is not None:
            value=Decimal(data['quantity_value'])
            if value!=value.to_integral_value():raise HTTPException(422,"A component count must be a whole number; select the source length unit for length quantities.")
            if data['quantity'] is not None and data['quantity']!=int(value):raise HTTPException(422,"Listed count and source count disagree.")
            data['quantity']=int(value)
    elif data['quantity_unit']!='unresolved':
        data['quantity']=None
        if len(data['evidence'].strip())<10:raise HTTPException(422,"A source quantity unit needs drawing/engineering evidence.")
    return data


@app.post("/api/v1/projects/{project_id}/materials")
def add_material(project_id: str, body: MaterialInput, actor=Depends(editor)):
    def update(p):
        sheet_for(p, body.sheet_id)
        p["materials"].append({**material_values(body), "id": uid()})
        p["materials_reviewed"] = False

    return change(
        project_id, body.version, actor, "Added materials inventory row", update
    )


@app.patch("/api/v1/projects/{project_id}/materials/{item_id}")
def patch_material(
    project_id: str, item_id: str, body: MaterialInput, actor=Depends(editor)
):
    def update(p):
        sheet_for(p, body.sheet_id)
        item = next((m for m in p["materials"] if m["id"] == item_id), None)
        if not item:
            raise HTTPException(404, "Material not found.")
        if any(
            item.get(key) != getattr(body, key)
            for key in ("family", "size", "description")
        ):
            item.pop("catalog_match", None)
            item.pop("spec_proposal",None)
            item["auto_match_disabled"]=True
        item.update(material_values(body))
        item["verification"]="reviewed"
        p["materials_reviewed"] = False

    return change(
        project_id, body.version, actor, "Corrected material inventory", update
    )


class ReviewInput(Version):
    materials_reviewed: bool
    layout_reviewed: bool


@app.post("/api/v1/projects/{project_id}/review")
def review(project_id: str, body: ReviewInput, actor=Depends(editor)):
    def update(p):
        p.update(body.model_dump(exclude={"version"}))
        p["status"] = "ENGINEERING_REVIEW"

    return change(
        project_id, body.version, actor, "Submitted for engineering review", update
    )


@app.get("/api/v1/projects/{project_id}/audit")
def history(project_id: str, actor=Depends(user)):
    with db() as conn:
        project_read(project_id, actor, conn)
        events = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM audit WHERE project_id=? ORDER BY rowid DESC LIMIT 200",
                (project_id,),
            )
        ]
        artifacts = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM artifacts WHERE project_id=? ORDER BY rowid DESC",
                (project_id,),
            )
        ]
        revisions = [
            {"version": r["version"], "updated": json.loads(r["data"])["updated"]}
            for r in conn.execute(
                "SELECT version,data FROM revisions WHERE id=? ORDER BY version DESC",
                (project_id,),
            )
        ]
    return {"events": events, "artifacts": artifacts, "revisions": revisions}


@app.post("/api/v1/projects/{project_id}/exports")
def export(project_id: str, body: Version, actor=Depends(editor)):
    diag.emit(DATA,"pdf.export.requested","DEBUG",revision=body.version)
    with db() as conn:
        project = project_read(project_id, actor, conn)
    if project["version"] != body.version:
        raise HTTPException(409, "Project has changed. Reload before exporting.")
    if not project["sheets"]:
        raise HTTPException(422, "Add a source PDF before exporting a review bundle.")
    from services.api.pipeline import publish_export
    try:
        with diag.stage(DATA,"pdf.export",revision=body.version):
            return publish_export(sys.modules[__name__],project,actor)
    except RuntimeError as exc:
        if str(exc)=="PROJECT_CHANGED":raise HTTPException(409,"Project changed while exporting. Regenerate from the latest revision.")
        raise
    except ValueError as exc:
        raise HTTPException(422,str(exc))


@app.get("/api/v1/projects/{project_id}/artifacts/{artifact_id}/download")
def download(project_id: str, artifact_id: str, actor=Depends(user)):
    with db() as conn:
        project_read(project_id, actor, conn)
        row = conn.execute(
            "SELECT * FROM artifacts WHERE id=? AND project_id=?",
            (artifact_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Artifact not found.")
    return FileResponse(
        DATA / "exports" / f"{artifact_id}.zip",
        media_type="application/zip",
        filename=row["filename"],
    )


@app.get("/api/v1/catalogs")
def catalogs(actor=Depends(user)):
    with db() as conn:
        return [
            {**dict(r), "data": json.loads(r["data"])}
            for r in conn.execute(
                "SELECT * FROM catalogs WHERE tenant=? ORDER BY rowid DESC",
                (actor["tenant"],),
            )
        ]


@app.post("/api/v1/catalogs/import")
async def import_catalog(file: UploadFile = File(...), actor=Depends(editor)):
    diag.emit(DATA,"catalog.import.started","DEBUG")
    if actor["role"] != "admin":
        raise HTTPException(403, "Administrator permission required.")
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(415, "Upload a non-macro XLSX workbook.")
    content = await file.read(15 * 1024 * 1024 + 1)
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(413, "Workbook exceeds 15 MB.")
    import io, zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 80 * 1024 * 1024 or any(
                "vbaProject" in i.filename for i in archive.infolist()
            ):
                raise ValueError("Unsafe workbook.")
        from openpyxl import load_workbook

        workbook = load_workbook(
            io.BytesIO(content), read_only=True, data_only=True, keep_links=False
        )
        sheets = [
            {"name": s.title, "rows": s.max_row, "columns": s.max_column}
            for s in workbook.worksheets
        ]
        workbook.close()
    except Exception as error:
        diag.exception(DATA,"catalog.import.rejected",error)
        raise HTTPException(
            422, "Invalid, oversized, encrypted or macro-enabled workbook."
        )
    record = {
        "id": uid(),
        "filename": Path(file.filename).name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "created": now(),
        "data": {
            "sheets": sheets,
            "status": "PENDING_SCHEMA_REVIEW",
            "note": "Immutable source registered. Engineering mapping and dataset approval are required before numeric use.",
        },
    }
    with db() as conn:
        (DATA / "catalogs" / f"{record['id']}.xlsx").write_bytes(content)
        conn.execute(
            "INSERT INTO catalogs VALUES (?,?,?,?,?,?)",
            (
                record["id"],
                actor["tenant"],
                record["filename"],
                record["sha256"],
                record["created"],
                json.dumps(record["data"]),
            ),
        )
    diag.emit(DATA,"catalog.import.completed",catalog_id=record["id"],worksheets=len(sheets),input_bytes=len(content))
    from packages.catalogs.canonical import SOURCE_SHA256
    if record['sha256'] == SOURCE_SHA256:
        from services.api.canonical_catalog import prepare_source
        prepare_source(sys.modules[__name__], record['id'], actor)
        record['data']['status'] = 'PREPARED_FOR_REVIEW'
    return record


from services.api.workflows import install

install(sys.modules[__name__])

from services.api.updates import install as install_updates
install_updates(sys.modules[__name__])

from services.api.pipeline import install as install_pipeline
install_pipeline(sys.modules[__name__])

from services.api.results import install as install_results
install_results(sys.modules[__name__])
from services.api.physical_model import install as install_physical_model
install_physical_model(sys.modules[__name__])
from services.api.source_review import install as install_source_review
install_source_review(sys.modules[__name__])
from services.api.source_coordinates import install as install_source_coordinates
install_source_coordinates(sys.modules[__name__])
from services.api.source_exceptions import install as install_source_exceptions
install_source_exceptions(sys.modules[__name__])
from services.api.stations import install as install_stations
install_stations(sys.modules[__name__])
from services.api.continuations import install as install_continuations
install_continuations(sys.modules[__name__])

from services.api.digitalocean import install as install_digitalocean
install_digitalocean(sys.modules[__name__])

from services.api.remote_pages import install as install_remote_pages
install_remote_pages(sys.modules[__name__])
from services.api.remote_setup import install as install_remote_setup
install_remote_setup(sys.modules[__name__])

from services.api.account_security import install as install_account_security
install_account_security(sys.modules[__name__])
from services.api.people import install as install_people
install_people(sys.modules[__name__])
from services.api.workspace_reset import install as install_workspace_reset
install_workspace_reset(sys.modules[__name__])
from services.api.review_flow import install as install_review_flow
install_review_flow(sys.modules[__name__])

from services.api.intake_guard import install as install_intake_guard
install_intake_guard(sys.modules[__name__])

diag.install(sys.modules[__name__])


@app.get("/loader.php", include_in_schema=False)
def project_loader():
    return FileResponse(ROOT / "loader.php", media_type="text/html")


@app.get("/LESSONS_LEARNED.md", include_in_schema=False)
def public_lessons_register():
    return FileResponse(ROOT / "LESSONS_LEARNED.md", media_type="text/markdown")


@app.api_route("/downloads/caesar-cpanel.zip", methods=["GET", "HEAD"], include_in_schema=False)
def hosting_package():
    path = ROOT / "downloads" / "caesar-cpanel.zip"
    if not path.is_file():
        raise HTTPException(404, "Build the hosting package with scripts/package_cpanel.py.")
    return FileResponse(path, media_type="application/zip", filename="caesar-cpanel.zip")


if (ROOT / "dist").exists():
    app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="web")
