"""Private bounded diagnostics, independent of the engineering database schema.

No request bodies, query values, headers, document text, filenames, exception
messages, console arguments or environment dumps are captured.
"""
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import traceback
from uuid import uuid4

CONTEXT = ContextVar("diagnostic_context", default=None)
_release_file=Path(__file__).resolve().parents[2]/"RELEASE.json"
VERSION=json.loads(_release_file.read_text()).get("version","unknown") if _release_file.exists() else "unknown"
MAX_ROWS = 20000
RETENTION_SECONDS = 7 * 86400
DROPPED = 0
LAST_NOTICE = 0.0
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
SOURCES = ("server", "browser", "updater")
PRIVATE_KEYS = re.compile(r"password|secret|token|authorization|cookie|body|payload|content|filename|email|raw|headers|environment", re.I)
UUID = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


def clean(value, depth=0):
    if depth > 5: return "[depth limited]"
    if isinstance(value, dict):
        return {str(k)[:60]: "[REDACTED]" if PRIVATE_KEYS.search(str(k)) else clean(v,depth+1) for k,v in list(value.items())[:40]}
    if isinstance(value, (tuple,list)): return [clean(v,depth+1) for v in value[:30]]
    if value is None or isinstance(value,(bool,int,float)): return value
    text = str(value)[:1000]
    for name, secret in os.environ.items():
        if re.search(r"password|secret|token|api_key|private_key",name,re.I) and len(secret)>=4:
            text=text.replace(secret,"[REDACTED]")
    text=re.sub(r"(?i)bearer\s+[^\s]+", "Bearer [REDACTED]",text)
    text=re.sub(r"(?i)(password|secret|token|api_key)\s*[:=]\s*[^\s,;]+",r"\1=[REDACTED]",text)
    text=re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}","[EMAIL]",text)
    return text


def connection(data):
    directory=Path(data)/"diagnostics"
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=directory/"events.sqlite3"
    conn=sqlite3.connect(path,timeout=0.25)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
    conn.execute("PRAGMA max_page_count=16384")
    conn.execute("""CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, level TEXT, source TEXT,
      event TEXT, request_id TEXT, actor_id TEXT, tenant TEXT, project_id TEXT,
      release TEXT, pid INTEGER, details TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS event_time ON events(at)")
    conn.execute("CREATE TABLE IF NOT EXISTS client_limits (actor TEXT PRIMARY KEY, bucket INTEGER, count INTEGER)")
    path.chmod(0o600)
    return conn


def bind_actor(actor):
    context=CONTEXT.get()
    if context is not None:
        context.update(actor_id=actor["id"],tenant=actor["tenant"])


@contextmanager
def database(data):
    conn=connection(data)
    try:
        with conn:yield conn
    finally:conn.close()


def metadata():
    context=CONTEXT.get() or {}
    scope=context.get("scope",{})
    project=scope.get("path_params",{}).get("project_id")
    return {"request_id":context.get("request_id"),"actor_id":context.get("actor_id"),"tenant":context.get("tenant"),"project_id":project if project and UUID.fullmatch(project) else None,"release":context.get("release",VERSION)}


def emit(data,event,level="INFO",source="server",**details):
    global DROPPED,LAST_NOTICE
    try:
        safe=clean(details)
        encoded=json.dumps(safe,ensure_ascii=True)
        if len(encoded)>8000: encoded=json.dumps({"truncated":True})
        fields=metadata()
        with database(data) as conn:
            conn.execute("INSERT INTO events(at,level,source,event,request_id,actor_id,tenant,project_id,release,pid,details) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(time.time(),level if level in LEVELS else "INFO",source if source in SOURCES else "server",event[:100],fields["request_id"],fields["actor_id"],fields["tenant"],fields["project_id"],fields["release"],os.getpid(),encoded))
            latest=conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            if latest%50==0:
                conn.execute("DELETE FROM events WHERE at<? OR id<=?",(time.time()-RETENTION_SECONDS,latest-MAX_ROWS))
                conn.execute("DELETE FROM client_limits WHERE bucket<?",(int(time.time()/60)-1440,))
                conn.execute("PRAGMA incremental_vacuum(128)")
    except Exception:
        DROPPED+=1
        # A diagnostics disk/lock failure must not take down normal operations.
        if DROPPED==1 or time.monotonic()-LAST_NOTICE>60:
            print("CAESAR diagnostic write failed; event omitted",file=sys.stderr)
            LAST_NOTICE=time.monotonic()


def exception(data,event,error,source="server",**details):
    frames=[{"file":Path(f.filename).name,"function":f.name,"line":f.lineno} for f in traceback.extract_tb(error.__traceback__)[-15:]]
    causes=[]
    for child in list(getattr(error,"exceptions",[]))[:5]:
        causes.append({"exception_type":type(child).__name__,"frames":[{"file":Path(f.filename).name,"function":f.name,"line":f.lineno} for f in traceback.extract_tb(child.__traceback__)[-8:]]})
    emit(data,event,"ERROR",source=source,exception_type=type(error).__name__,frames=frames,causes=causes,**details)


@contextmanager
def stage(data,event,**details):
    start=time.perf_counter()
    emit(data,event+".started","DEBUG",**details)
    try:
        yield
    except Exception as error:
        exception(data,event+".failed",error,duration_ms=round((time.perf_counter()-start)*1000,2),**details)
        raise
    else:
        emit(data,event+".completed",duration_ms=round((time.perf_counter()-start)*1000,2),**details)


class DiagnosticMiddleware:
    def __init__(self,app,data,release): self.app,self.data,self.release=app,data,release
    async def __call__(self,scope,receive,send):
        if scope["type"]!="http": return await self.app(scope,receive,send)
        identity=uuid4().hex
        context={"request_id":identity,"release":self.release,"scope":scope}
        token=CONTEXT.set(context)
        started=False;status=500;received=0;sent=0;finished=False;failed=False
        begin=time.perf_counter()
        internal="/api/v1/system/logs" in scope.get("path","")
        async def incoming():
            nonlocal received
            message=await receive()
            received+=len(message.get("body",b""))
            return message
        async def outgoing(message):
            nonlocal started,status,sent,finished
            if message["type"]=="http.response.start":
                started=True;status=message["status"]
                message["headers"]=list(message.get("headers",[]))+[(b"x-request-id",identity.encode())]
            if message["type"]=="http.response.body":
                sent+=len(message.get("body",b""));finished=not message.get("more_body",False)
            await send(message)
        try:
            if not internal:emit(self.data(),"http.started","DEBUG",method=scope["method"])
            await self.app(scope,incoming,outgoing)
        except Exception as error:
            failed=True
            exception(self.data(),"http.exception",error)
            if started:raise
            body=json.dumps({"detail":"Unexpected server error. Share the request ID from Logs.","request_id":identity}).encode()
            await outgoing({"type":"http.response.start","status":500,"headers":[(b"content-type",b"application/json"),(b"cache-control",b"no-store"),(b"x-content-type-options",b"nosniff")]})
            await outgoing({"type":"http.response.body","body":body})
        finally:
            route=getattr(scope.get("route"),"path","unmatched")
            if not internal or status>=400:
                emit(self.data(),"http.completed","ERROR" if status>=500 or failed else "WARNING" if status>=400 else "INFO",method=scope["method"],route=route,status=status,duration_ms=round((time.perf_counter()-begin)*1000,2),received_bytes=received,sent_bytes=sent,complete=finished,stream_failed=failed)
            CONTEXT.reset(token)


def query(data,q="",level="",source="",hours=24,before=0,limit=100):
    where=["at>=?"];args=[time.time()-hours*3600]
    if level:where.append("level=?");args.append(level)
    if source:where.append("source=?");args.append(source)
    if before:where.append("id<?");args.append(before)
    if q:
        where.append("(event LIKE ? OR request_id LIKE ? OR project_id LIKE ? OR details LIKE ?)")
        args.extend(["%"+q+"%"]*4)
    with database(data) as conn:
        rows=conn.execute("SELECT * FROM events WHERE "+" AND ".join(where)+" ORDER BY id DESC LIMIT ?",[*args,limit]).fetchall()
        totals={row["level"]:row["n"] for row in conn.execute("SELECT level,COUNT(*) n FROM events WHERE at>=? GROUP BY level",(time.time()-hours*3600,))}
        total=conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    result=[]
    for row in rows:
        item=dict(row);item["details"]=json.loads(item["details"])
        item["timestamp"]=datetime.fromtimestamp(item.pop("at"),timezone.utc).isoformat()
        result.append(item)
    return {"events":result,"totals":totals,"stored_events":total,"next_before":result[-1]["id"] if len(result)==limit else None,"retention_days":7,"max_events":MAX_ROWS,"dropped_in_this_process":DROPPED}


def install(api):
    from fastapi import Depends,HTTPException,Query,Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel,ConfigDict,Field,ValidationError
    from typing import Literal
    class BrowserEvent(BaseModel):
        model_config=ConfigDict(extra="forbid")
        kind:Literal["navigation","api","error","rejection","console","resource","action"]
        action:Literal["none","load_project","upload_pdf","export_bundle","save_node","save_annotation","form_invalid","check_updates","install_update","rollback_update"]="none"
        client_at:float=Field(default=0,ge=0,le=4000000000000,allow_inf_nan=False)
        view:Literal["projects","workspace","sheets","materials","validation","activity","catalogs","logs","login","unknown"]="unknown"
        request_id:str=Field(default="",pattern=r"^(?:[a-f0-9]{32})?$",max_length=32)
        status:int=Field(default=0,ge=0,le=599)
        duration_ms:float=Field(default=0,ge=0,le=3600000,allow_inf_nan=False)
        error_type:Literal["Error","TypeError","ReferenceError","SyntaxError","RangeError","URIError","EvalError","AggregateError","DOMException","UnknownError"]="UnknownError"
        frame:str=Field(default="",pattern=r"^(?:[\w.-]+\.(?:js|mjs|tsx?):[0-9]+:[0-9]+)?$",max_length=180)
    class BrowserBatch(BaseModel):
        model_config=ConfigDict(extra="forbid")
        events:list[BrowserEvent]=Field(max_length=20,min_length=1)
    def operator(actor=Depends(api.user)):
        if actor["role"]!="admin" or (not api.LOCAL_DEMO and actor["id"]!="admin"):
            raise HTTPException(403,"Hosting administrator access required")
        return actor
    def filters(q:str=Query("",max_length=200),level:str=Query("",pattern="^(DEBUG|INFO|WARNING|ERROR)?$"),source:str=Query("",pattern="^(server|browser|updater)?$"),hours:int=Query(24,ge=1,le=168),before:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200)):
        return dict(q=q,level=level,source=source,hours=hours,before=before,limit=limit)
    @api.app.get("/api/v1/system/logs")
    def logs(selection=Depends(filters),actor=Depends(operator)):
        return query(api.DATA,**selection)
    @api.app.get("/api/v1/system/logs/export")
    def export_logs(selection=Depends(filters),actor=Depends(operator)):
        selection.update(limit=2000)
        report=query(api.DATA,**selection)
        report.update(format="caesar-diagnostics-v1",release=api.BUILD_ID,generated_at=datetime.now(timezone.utc).isoformat(),python=sys.version.split()[0],platform=sys.platform,display_timezone="Australia/Sydney",privacy="No request bodies, query values, headers, filenames, drawing text, raw exception messages, console arguments or environment dumps. Review before sharing.",coverage="Instrumented application/browser/update events only; not provider OS/Apache/Passenger logs before application startup.")
        return JSONResponse(report,headers={"Content-Disposition":'attachment; filename="caesar-diagnostics.json"'})
    @api.app.post("/api/v1/system/logs/client")
    async def browser_events(request:Request,actor=Depends(api.user)):
        chunks=bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks)>32768:raise HTTPException(413,"Diagnostic batch exceeds limit")
        try:batch=BrowserBatch.model_validate_json(chunks)
        except ValidationError:raise HTTPException(422,"Invalid structured diagnostic batch")
        with database(api.DATA) as conn:
            conn.execute("BEGIN IMMEDIATE")
            bucket=int(time.time()/60)
            conn.execute("INSERT INTO client_limits VALUES (?,?,?) ON CONFLICT(actor) DO UPDATE SET count=CASE WHEN bucket=excluded.bucket THEN count+excluded.count ELSE excluded.count END,bucket=excluded.bucket",(actor["id"],bucket,len(batch.events)))
            if conn.execute("SELECT count FROM client_limits WHERE actor=?",(actor["id"],)).fetchone()[0]>120:
                conn.rollback();raise HTTPException(429,"Diagnostic rate limit reached")
        for item in batch.events:
            context=CONTEXT.get()
            original=context["request_id"]
            if item.request_id:context["request_id"]=item.request_id
            emit(api.DATA,"browser."+item.kind,"ERROR" if item.kind in ("error","rejection") or item.status>=500 or (item.kind=="api" and item.status==0) else "WARNING" if item.kind in ("console","resource") or item.status>=400 else "INFO",source="browser",view=item.view,action=item.action,client_at_ms=item.client_at,status=item.status,duration_ms=item.duration_ms,error_type=item.error_type,frame=item.frame,untrusted_client=True)
            context["request_id"]=original
        return {"accepted":len(batch.events)}
    api.app.add_middleware(DiagnosticMiddleware,data=lambda:api.DATA,release=api.BUILD_ID)
