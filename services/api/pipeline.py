"""Durable, fenced drawing jobs. Passenger only accepts input and reads progress."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import sqlite3
import time

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from packages.automation import VERSION
from packages.automation.contracts import PageEvidence
from packages.automation.recognize import identity, layout, materials, node_proposals, text_rows, vector_graph
from packages.automation.routes import propose as propose_routes
from packages.catalogs import exact_match
from packages.engineering import compute_reasons, renumber, validate
from packages.pdf import export_bundle
from services.api import diagnostics as diag
from services.api.pipeline_executor import execute, WorkerUnavailable
from services.api.updates import write

TERMINAL = {"DONE","FAILED","CANCELLED","SUPERSEDED"}
STAGES = ["register","extract","compose","export"]


def schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS pipeline_runs (
      id TEXT PRIMARY KEY, project_id TEXT, tenant TEXT, actor TEXT, source_id TEXT,
      sha TEXT, filename TEXT, base_revision INTEGER, revision INTEGER,
      state TEXT, stage TEXT, fence INTEGER DEFAULT 0, lease REAL DEFAULT 0,
      attempts INTEGER DEFAULT 0, next_at REAL DEFAULT 0, created REAL, updated REAL,
      options TEXT, progress TEXT, error TEXT, UNIQUE(project_id,sha,options,base_revision));
    CREATE INDEX IF NOT EXISTS pipeline_pending ON pipeline_runs(state,next_at,created);
    CREATE TABLE IF NOT EXISTS pipeline_events (id INTEGER PRIMARY KEY, run_id TEXT,
      stage TEXT, state TEXT, at REAL, details TEXT);
    CREATE TABLE IF NOT EXISTS artifact_keys (project_id TEXT, revision INTEGER,
      purpose TEXT, artifact_id TEXT, PRIMARY KEY(project_id,revision,purpose));
    CREATE TABLE IF NOT EXISTS intake_limits (key TEXT PRIMARY KEY,bucket INTEGER,count INTEGER);
    CREATE TABLE IF NOT EXISTS pipeline_outbox (project_id TEXT, revision INTEGER, actor TEXT, created REAL,
      PRIMARY KEY(project_id,revision));
    """)
    from services.api.remote_pages import schema as remote_schema
    remote_schema(conn)


def public(row):
    value = dict(row)
    return {k:value[k] for k in ("id","project_id","state","stage","created","updated","revision","error")} | {
        "progress":json.loads(value["progress"]),"software":VERSION}


def events(conn,run,stage,state,**details):
    conn.execute("INSERT INTO pipeline_events(run_id,stage,state,at,details) VALUES (?,?,?,?,?)",
                 (run,stage,state,time.time(),json.dumps(details)))


def pinned_catalogs(conn,tenant):
    chosen = {}
    for row in conn.execute("SELECT * FROM catalog_versions WHERE tenant=? ORDER BY seq",(tenant,)):
        data=json.loads(row["data"])
        if data.get("status")=="APPROVED":chosen[row["catalog_id"]]=row["id"]
    return sorted(chosen.values())


def enqueue(api,project,actor,source_id,sha,filename,replace=None,cached=None):
    options=json.dumps({"replace_source_id":replace,"cached_from":cached,"version":VERSION},sort_keys=True)
    with api.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if (api.DATA/'updates/maintenance.json').exists():raise HTTPException(503,'Workspace maintenance is running. Retry shortly.')
        current=api.project_read(project['id'],actor,conn)
        if current['version']!=project['version']:raise HTTPException(409,'Project changed before the job was accepted. Reload and retry.')
        found=conn.execute("SELECT * FROM pipeline_runs WHERE project_id=? AND sha=? AND options=? AND base_revision=?",
                           (project["id"],sha,options,project["version"])).fetchone()
        if found:return public(found)
        active_project=conn.execute("SELECT COUNT(*) FROM pipeline_runs WHERE project_id=? AND state NOT IN ('DONE','FAILED','CANCELLED','SUPERSEDED')",(project["id"],)).fetchone()[0]
        if active_project>=10:raise HTTPException(429,"Ten drawing jobs are already queued for this project.")
        active=conn.execute("SELECT COUNT(*) FROM pipeline_runs WHERE tenant=? AND state NOT IN ('DONE','FAILED','CANCELLED','SUPERSEDED')",(actor["tenant"],)).fetchone()[0]
        if active>=100:raise HTTPException(429,"This workspace has 100 pending drawing jobs. Let processing finish first.")
        recent=conn.execute("SELECT COUNT(*) FROM pipeline_runs WHERE tenant=? AND created>?",(actor["tenant"],time.time()-86400)).fetchone()[0]
        if recent>=500:raise HTTPException(429,"Daily drawing job allowance reached.")
        run=api.uid(); now=time.time()
        input_bytes=(api.DATA/"sources"/f"{source_id}.pdf").stat().st_size
        stored=conn.execute("SELECT progress FROM pipeline_runs WHERE tenant=?",(actor["tenant"],)).fetchall()
        usage=sum(json.loads(v["progress"]).get("input_bytes",0) for v in stored)
        if not cached and usage+input_bytes>500*1024**2:raise HTTPException(413,"Automatic intake storage allowance reached. Review private storage before adding drawings.")
        progress={"pages":0,"page":0,"input_bytes":0 if cached else input_bytes,"catalog_versions":pinned_catalogs(conn,actor["tenant"]),"application_release":api.BUILD_ID}
        from services.api.remote_setup import policy as remote_policy
        progress['processor'] = 'digitalocean' if remote_policy(api.DATA)['enabled'] else 'hosting'
        stage="compose" if cached else "register"
        if cached:
            previous=conn.execute("SELECT progress FROM pipeline_runs WHERE id=? AND project_id=?",(cached,project["id"])).fetchone()
            if not previous:raise HTTPException(409,"Previous extraction is unavailable.")
            progress.update(json.loads(previous["progress"]))
            progress.pop("artifact",None)
            progress["input_bytes"]=0
            progress["application_release"]=api.BUILD_ID
        conn.execute("INSERT INTO pipeline_runs(id,project_id,tenant,actor,source_id,sha,filename,base_revision,revision,state,stage,created,updated,options,progress) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (run,project["id"],actor["tenant"],actor["id"],source_id,sha,filename,project["version"],project["version"] if cached else None,"QUEUED",stage,now,now,options,json.dumps(progress)))
        events(conn,run,stage,"QUEUED")
        row=conn.execute("SELECT * FROM pipeline_runs WHERE id=?",(run,)).fetchone()
    diag.emit(api.DATA,"pipeline.queued",run_id=run,project_id=project["id"])
    return public(row)


def claim(api):
    with api.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        # A crashed worker's lease expires; a new fencing token invalidates it.
        row=conn.execute("""SELECT r.* FROM pipeline_runs r WHERE
          (r.state IN ('QUEUED','RETRY_WAIT','WAITING_WORKER') OR (r.state='RUNNING' AND r.lease<?)) AND r.next_at<=?
          AND NOT EXISTS (SELECT 1 FROM pipeline_runs q WHERE q.project_id=r.project_id AND q.id<>r.id
            AND q.state NOT IN ('DONE','FAILED','CANCELLED','SUPERSEDED')
            AND (q.created<r.created OR (q.state='RUNNING' AND q.lease>?))) ORDER BY r.created LIMIT 1""",(time.time(),time.time(),time.time())).fetchone()
        if not row:return None
        conn.execute("UPDATE pipeline_runs SET state='RUNNING',fence=fence+1,lease=?,attempts=attempts+1,updated=? WHERE id=?",(time.time()+300,time.time(),row["id"]))
        row=dict(conn.execute("SELECT * FROM pipeline_runs WHERE id=?",(row["id"],)).fetchone())
        events(conn,row["id"],row["stage"],"RUNNING",fence=row["fence"])
        return row


def fenced(conn,job):
    row=conn.execute("SELECT * FROM pipeline_runs WHERE id=? AND state='RUNNING' AND fence=? AND lease>?",(job["id"],job["fence"],time.time())).fetchone()
    if not row:raise RuntimeError("STALE_ATTEMPT")
    return row


def heartbeat(api,job):
    with api.db() as conn:
        conn.execute("UPDATE pipeline_runs SET lease=?,updated=? WHERE id=? AND state='RUNNING' AND fence=?",(time.time()+300,time.time(),job["id"],job["fence"]))


def advance(api,job,progress,next_stage=None,state="QUEUED",error=None,next_at=0):
    with api.db() as conn:
        conn.execute("BEGIN IMMEDIATE");fenced(conn,job)
        conn.execute("UPDATE pipeline_runs SET progress=?,stage=?,state=?,error=?,updated=?,lease=0,attempts=0,next_at=? WHERE id=?",
                     (json.dumps(progress),next_stage or job["stage"],state,error,time.time(),next_at,job["id"]))
        events(conn,job["id"],job["stage"],"DONE" if state=="QUEUED" else state)


def actor_for(api,job,conn):
    row=conn.execute("SELECT * FROM users WHERE id=? AND tenant=?",(job["actor"],job["tenant"])).fetchone()
    if not row or row["role"] not in ('admin','engineer'):raise PermissionError("AUTHOR_PERMISSION_REVOKED")
    from services.api.account_security import active
    if not active(conn,row['id']):raise PermissionError('AUTHOR_PERMISSION_REVOKED')
    return dict(row)


def commit_project(api,conn,job,project,action,preserve_status=False):
    fenced(conn,job)
    from packages.engineering import refresh_source_locations
    refresh_source_locations(project)
    from packages.physical import prepare as prepare_physical
    prepare_physical(project)
    from packages.engineering.graph_review import renumber_project
    renumber_project(project,action,job.get('actor'),api.now())
    from packages.physical.stations import apply_station_reasons
    apply_station_reasons(project)
    from packages.physical.source_exceptions import refresh_source_exceptions
    refresh_source_exceptions(project)
    from packages.engineering.graph_review import apply_topology_reasons
    apply_topology_reasons(project)
    compute_reasons(project["nodes"])
    project["version"]+=1;project["updated"]=api.now()
    if not preserve_status:project["status"]="DRAFT"
    project.pop("review_approval",None)
    conn.execute("UPDATE projects SET version=?,data=? WHERE id=?",(project["version"],json.dumps(project),project["id"]))
    conn.execute("INSERT INTO revisions VALUES (?,?,?)",(project["id"],project["version"],json.dumps(project)))
    conn.execute("UPDATE pipeline_runs SET revision=?,updated=? WHERE id=?",(project["version"],time.time(),job["id"]))
    api.audit(conn,project["id"],"Drawing pipeline",action)


def register(api,job,progress):
    path=api.DATA/"sources"/f"{job['source_id']}.pdf"
    if hashlib.sha256(path.read_bytes()).hexdigest()!=job["sha"]:raise ValueError("SOURCE_HASH_MISMATCH")
    pages=execute(path,"register",heartbeat=lambda:heartbeat(api,job))
    if not isinstance(pages,list) or not 1<=len(pages)<=100:raise ValueError("INVALID_PAGE_RESULT")
    options=json.loads(job["options"])
    with api.db() as conn:
        conn.execute("BEGIN IMMEDIATE");fenced(conn,job)
        actor=actor_for(api,job,conn);p=api.project_read(job["project_id"],actor,conn)
        own=[s for s in p["sheets"] if s["source_id"]==job["source_id"]]
        if own:
            progress.update(pages=len(own),page=0,sheets=[s["id"] for s in own],revision=p["version"])
            conn.execute('UPDATE pipeline_runs SET revision=?,updated=? WHERE id=?',(p['version'],time.time(),job['id']))
            resumed=True
        else:resumed=False
    if resumed:
        advance(api,job,progress,"extract");return
    with api.db() as conn:
        conn.execute("BEGIN IMMEDIATE");fenced(conn,job)
        actor=actor_for(api,job,conn);p=api.project_read(job["project_id"],actor,conn)
        replace=options["replace_source_id"]
        if replace and p["version"]!=job["base_revision"]:raise RuntimeError("PROJECT_CHANGED")
        old=[s for s in p["sheets"] if s["source_id"]==replace] if replace else []
        if replace and not old:raise RuntimeError("REVISION_TARGET_CHANGED")
        if any(s["sha256"]==job["sha"] and s['source_id']!=replace for s in p["sheets"]):
            raise RuntimeError("SOURCE_ALREADY_ACTIVE")
        if len(p["sheets"])-len(old)+len(pages)>200:raise ValueError("PROJECT_PAGE_LIMIT")
        matches={}
        for page in pages:
            candidates=[s for s in old if s.get("content_hash") and s["content_hash"]==page.get("content_hash") and
                        s["width"]==page["width"] and s["height"]==page["height"]]
            if len(candidates)==1 and sum(q.get("content_hash")==page.get("content_hash") for q in pages)==1:
                matches[page["page_index"]]=candidates[0]
        preserved={s["id"] for s in matches.values()}
        old_ids={s["id"] for s in old}-preserved
        if old:
            p.setdefault("source_history",[]).append(deepcopy({"source_id":replace,"superseded_by":job["source_id"],
                "sheets":old,"nodes":[n for n in p["nodes"] if any(v["sheet_id"] in old_ids for v in n["instances"])],
                "materials":[m for m in p["materials"] if m["sheet_id"] in old_ids],
                "annotations":[a for a in p.get("annotations",[]) if a["sheet_id"] in old_ids]}))
            p["sheets"]=[s for s in p["sheets"] if s["source_id"]!=replace]
            for node in p["nodes"]:node["instances"]=[v for v in node["instances"] if v["sheet_id"] not in old_ids]
            p["nodes"]=[n for n in p["nodes"] if n["instances"]]
            retained={n["id"] for n in p["nodes"]}
            for node in p["nodes"]:
                if node.get("takeoff_id") not in retained:node["takeoff_id"]=None
            p["materials"]=[m for m in p["materials"] if m["sheet_id"] not in old_ids]
            p["annotations"]=[a for a in p.get("annotations",[]) if a["sheet_id"] not in old_ids]
        sheets=[]
        for page in pages:
            if not isinstance(page,dict) or not 0<=page["page_index"]<len(pages):raise ValueError("INVALID_PAGE_RESULT")
            previous=matches.get(page["page_index"],{})
            sheet={**previous,**page,"id":previous.get("id") or identity(p["id"],job["sha"],page["page_index"]),"source_id":job["source_id"],
                   "filename":job["filename"],"sha256":job["sha"],"printed_id":"","line_id":p["line_id"],"axis":None,"table":None}
            for key in ("printed_id","line_id","axis","table"):
                if key in previous:sheet[key]=previous[key]
            p["sheets"].append(sheet);sheets.append(sheet["id"])
        if replace:p.setdefault("revision_changes",[]).append({"previous_source_id":replace,"source_id":job["source_id"],"sha256":job["sha"],"unchanged_sheet_ids":sorted(preserved),"changed_or_removed_sheet_ids":sorted(old_ids),"new_sheet_ids":[s for s in sheets if s not in preserved],"at":api.now(),"engineering_correspondence":"Only identical unique content streams retain identity; changed locations require review."})
        conn.execute("INSERT INTO sources VALUES (?,?,?,?)",(job["source_id"],p["id"],job["filename"],job["sha"]))
        p["materials_reviewed"]=False;p["layout_reviewed"]=False
        p["automation"]={"run_id":job["id"],"software":VERSION,"state":"PROCESSING","issues":[]}
        if old_ids:p["automation"]["issues"].append({"code":"REVISION_REBASE_REQUIRED","severity":"critical","message":"Changed pages are active. Previous engineering points/notes are archived for explicit reconciliation. Unchanged matched pages retain their identities.","archived_source_id":replace})
        commit_project(api,conn,job,p,"Registered drawing revision" if old else "Registered drawing pack")
        progress.update(pages=len(pages),page=0,sheets=sheets,all_sheets=len(p["sheets"]),revision=p["version"])
    advance(api,job,progress,"extract")


def page_path(api,run,page):
    return api.DATA/"pipeline"/run/f"page-{page}.json"


def load_pages(api,job,progress):
    result={};size=0
    with api.db() as conn:
        rows=conn.execute("SELECT id,progress FROM pipeline_runs WHERE project_id=? ORDER BY created DESC",(job["project_id"],)).fetchall()
        project=json.loads(conn.execute("SELECT data FROM projects WHERE id=?",(job["project_id"],)).fetchone()[0])
        active={s["id"] for s in project["sheets"]}
    for row in rows:
        state=json.loads(row["progress"]);owner=state.get("evidence_run",row["id"])
        for i,sheet in enumerate(state.get("sheets",[])):
            path=page_path(api,owner,i)
            if sheet in active and sheet not in result and path.exists():
                size+=path.stat().st_size
                if size>64*1024**2:raise ValueError("EVIDENCE_SET_LIMIT")
                result[sheet]=json.loads(path.read_text())
                result[sheet]["_owner_run"]=owner;result[sheet]["_owner_page"]=i
    return result


def publish_page_review(api,conn,job,index,evidence):
    """Expose source observations early; human edits win during final compose."""
    actor=actor_for(api,job,conn)
    p=api.project_read(job['project_id'],actor,conn)
    sheet=next((s for s in p['sheets'] if s['source_id']==job['source_id'] and s['page_index']==index),None)
    if not sheet:raise RuntimeError('SOURCE_ALREADY_ACTIVE')
    found,exceptions,ledger=materials(evidence,sheet,job['sha'])
    excluded=set(p.get('automation_tombstones',{}).get('material_ids',[]))
    existing={m['id'] for m in p['materials']}
    p['materials'].extend(m for m in found if m['id'] not in existing|excluded)
    if evidence.get('ocr_used'):
        sheet['ocr_text']='\n'.join(r['text'] for r in text_rows(evidence['words']))[:100000]
    partial=p.setdefault('automation',{})
    partial.setdefault('partial_pages',{})[sheet['id']]={
        'source_sha256':job['sha'],'page_index':index,'run_id':job['id'],
        'state':'AVAILABLE_FOR_REVIEW','material_ids':[m['id'] for m in found]}
    partial['processing_run']=job['id']
    partial['state']='PROCESSING'
    partial.setdefault('issues',[])
    partial['issues']=[i for i in partial['issues'] if i['code']!='PAGES_PENDING_PROCESSING']
    partial['issues'].append({'code':'PAGES_PENDING_PROCESSING','severity':'critical',
                              'message':'Drawing processing is still running. This review draft is incomplete.'})
    existing_issues={json.dumps(i,sort_keys=True) for i in partial['issues']}
    for issue in exceptions:
        value={**issue,'severity':'critical','message':issue['code'].replace('_',' ').capitalize()}
        if json.dumps(value,sort_keys=True) not in existing_issues:partial['issues'].append(value)
    p['materials_reviewed']=False
    commit_project(api,conn,job,p,'Made a processed drawing page available for review')


def extract(api,job,progress):
    if progress.get('processor') == 'digitalocean':
        from services.api.remote_pages import step
        return step(api, job, progress)
    i=progress["page"]
    path=api.DATA/"sources"/f"{job['source_id']}.pdf"
    if hashlib.sha256(path.read_bytes()).hexdigest()!=job["sha"]:raise ValueError("SOURCE_HASH_MISMATCH")
    result=PageEvidence.model_validate(execute(path,"ocr",i,heartbeat=lambda:heartbeat(api,job))).model_dump(mode="json")
    if result.get("page_index")!=i or result["source_sha256"]!=job["sha"] or not isinstance(result.get("words"),list) or len(result["words"])>30000:
        raise ValueError("INVALID_EVIDENCE_RESULT")
    # Result is staged per attempt, then fence checked before publishing checkpoint.
    staged=page_path(api,job["id"],i).with_suffix(f".{job['fence']}.staged")
    write(staged,result)
    with api.db() as conn:
        conn.execute("BEGIN IMMEDIATE");fenced(conn,job)
        os.replace(staged,page_path(api,job["id"],i))
    progress["page"]+=1;progress["evidence_run"]=job["id"]
    progress["ocr_pages"]=progress.get("ocr_pages",0)+int(result.get("ocr_used",False))
    progress["isolation"]=result.get("isolation")
    advance(api,job,progress,"compose" if progress["page"]==progress["pages"] else "extract")


def compose(api,job,progress):
    pages=load_pages(api,job,progress)
    with api.db() as conn:
        actor=actor_for(api,job,conn);p=api.project_read(job["project_id"],actor,conn)
    expected=job["revision"]
    if p["version"]!=expected:raise RuntimeError("PROJECT_CHANGED")
    if p.get("automation",{}).get("run_id")==job["id"] and p["automation"].get("state")=="REVIEW_DRAFT":
        progress.update(revision=p["version"],coverage=p["automation"]["coverage"],exceptions=len(p["automation"]["issues"]))
        progress["evidence_pages"]=p["automation"].get("evidence_pages",[])
        progress["pages"]=len(p["sheets"])
        advance(api,job,progress,"export");return
    working=deepcopy(p);issues=[i for i in working.get("automation",{}).get("issues",[]) if i["code"]=="REVISION_REBASE_REQUIRED"]
    active_ids={s["id"] for s in working["sheets"]};pages={k:v for k,v in pages.items() if k in active_ids}
    inventory_ledger=[];graphs=[];proposals=[];new_materials=[];features=[];continuation_candidates=[]
    from packages.engineering.continuations import source_candidates,candidate_matches,LIMIT as CONTINUATION_LIMIT
    for sheet in working["sheets"]:
        page=pages.get(sheet["id"])
        if not page:
            issues.append({"code":"SOURCE_EVIDENCE_NOT_AVAILABLE","sheet_id":sheet["id"]});continue
        rows=text_rows(page["words"])
        text="\n".join(row["text"] for row in rows)
        sheet["identity_evidence"]=[]
        if page.get("ocr_used"):sheet["ocr_text"]=text[:100000]
        for code in page.get("issues",[]):issues.append({"code":code,"sheet_id":sheet["id"]})
        title=next((r for r in rows if re.search(r"\bSHEET\s+\d+\s+(?:OF|/)\s*\d+",r["text"],re.I)),None)
        if title and not sheet["printed_id"]:sheet["printed_id"]=title["text"][:150]
        for row in rows:
            if "LINE" in row["text"].upper() or working["line_id"] in row["text"]:
                sheet.setdefault("identity_evidence",[]).append({"text":row["text"][:300],"bbox":row["bbox"],"verification":"proposed"})
            if row["y"]>sheet["height"]*.75 or re.search(r"\bLINE\s*(?:ID|NO)[.:]?",row["text"],re.I):
                candidate=re.search(r'\b\d+["”]?\s*-\s*[A-Z0-9]+(?:-[A-Z0-9./]+){2,}',row["text"],re.I)
                if candidate:sheet["line_id_proposal"]=re.sub(r'["”\s]','',candidate[0])
        if not sheet.get("identity_verified"):
            issues.append({"code":"DRAWING_IDENTITY_REVIEW_REQUIRED","sheet_id":sheet["id"],"message":"Confirm the printed full line and sheet identity in the drawing register; OCR proposals are not approval."})
        items,exceptions,ledger=materials(page,sheet,sheet["sha256"])
        if len(continuation_candidates)<CONTINUATION_LIMIT:
            found_continuations=source_candidates(page,sheet)
            continuation_candidates.extend(found_continuations[:CONTINUATION_LIMIT-len(continuation_candidates)])
            if len(found_continuations)>=100:issues.append({'code':'CONTINUATION_SHEET_CANDIDATE_LIMIT','sheet_id':sheet['id']})
        else:issues.append({'code':'CONTINUATION_CANDIDATE_LIMIT','sheet_id':sheet['id']})
        new_materials+=items;issues+=exceptions;inventory_ledger+=ledger
        nodes,exceptions=node_proposals(page,sheet,sheet["sha256"])
        proposals+=nodes;issues+=exceptions
        for symbol in page.get('symbols',[]):
            features.append({**symbol,'id':identity(sheet['id'],symbol['profile'],symbol['flange_face'],symbol['opposite_pipe_dot']),
                             'sheet_id':sheet['id'],'source_sha256':sheet['sha256'],
                             'source_content_hash':sheet.get('content_hash'),'verification':'proposed'})
            issues.append({'code':'FLANGE_LOCATION_REVIEW_REQUIRED','sheet_id':sheet['id'],
                           'feature_id':symbol['id'],'bbox':symbol['bbox'],
                           'message':'Inspect the proposed flange face and separate pipe dot in Detected features. Material identity, route and physical station remain unverified.'})
        graphs.append({"sheet_id":sheet["id"],"page_width":sheet["width"],"page_height":sheet["height"],**vector_graph(page)})
        if not nodes and not any(any(v["sheet_id"]==sheet["id"] for v in n["instances"]) for n in working["nodes"]):issues.append({"code":"PHYSICAL_ROUTE_REVIEW_REQUIRED","sheet_id":sheet["id"]})
    existing_ids={m["id"] for m in working["materials"]}
    excluded_materials=set(working.get("automation_tombstones",{}).get("material_ids",[]))
    from packages.physical.source_review import incoming_materials
    working["materials"].extend(m for m in incoming_materials(working,new_materials) if m["id"] not in existing_ids|excluded_materials)
    existing_nodes={n["id"] for n in working["nodes"]}
    # Explicit source route/order profiles can prepare a model; generic centreline
    # candidates stay separate until an engineer establishes route identity/order.
    aliases=set(working.get('point_aliases',{}))
    excluded_nodes=set(working.get("automation_tombstones",{}).get("node_ids",[]))|aliases
    working["nodes"].extend(n for n in proposals if n["id"] not in existing_nodes|excluded_nodes and n["route"]=="main")
    for node in proposals:
        if node["id"] in excluded_nodes-aliases:issues.append({"code":"POINT_EXCLUDED_BY_REVIEW","point_id":node["id"],"severity":"review"})
    for n in proposals:
        if n["route"]!="main" and n['id'] not in aliases:issues.append({"code":"BRANCH_TAKEOFF_REVIEW_REQUIRED","point_id":n["id"]})
    with api.db() as conn:
        datasets=[]
        for version in progress["catalog_versions"]:
            row=conn.execute("SELECT * FROM catalog_versions WHERE id=? AND tenant=?",(version,job["tenant"])).fetchone()
            if row:
                data=json.loads(row["data"])
                if data.get("status")=="APPROVED":datasets.append((dict(row),data))
        for item in working["materials"]:
            if item.get("catalog_match") or item.get("auto_match_disabled") or item["family"] not in ("flange","valve"):continue
            matches=[];ambiguous=False
            for row,data in datasets:
                found=exact_match(data.get("records",[]),item.get("spec_proposal",{}))
                if found["status"]=="AMBIGUOUS_MATCH":ambiguous=True
                if found["status"]=="EXACT_MATCH":matches.append((row,data,found["candidates"][0]))
            if len(matches)==1 and not ambiguous:
                row,data,record=matches[0]
                item["catalog_match"]={"catalog_version_id":row["id"],"spec":item["spec_proposal"],
                                       "record":deepcopy(record),"status":"REFERENCE_ONLY", "match_method":"automation-exact",
                                       "catalog_source_sha256":data["source_sha256"],"catalog_records_sha256":data["records_sha256"],"catalog_approval":data["approval"],
                                       "reason":"Unique exact source-specification proposal; manufacturer identity and engineering use remain unapproved.","matched_by":"Automatic exact matcher","matched_at":api.now()}
            else:issues.append({"code":"CATALOG_MATCH_REVIEW_REQUIRED","material_id":item["id"],"match_count":len(matches)})
    material_by_evidence={m.get("evidence_id"):m for m in working["materials"]}
    material_by_id={m["id"]:m for m in working["materials"]}
    issues=[i for i in issues if not (
        i["code"]=="ITEM_NOT_LOCATED" and material_by_id.get(i.get("material_id"),{}).get("observed",0)>0
        or i["code"] in ("UNREADABLE_ITEM_NUMBER","UNRESOLVED_QUANTITY") and material_by_evidence.get(i.get("evidence_id"),{}).get("verification")=="reviewed")]
    old_layout=[(s.get("axis"),s.get("table")) for s in p["sheets"]]
    issues+=layout(working,pages)
    dedup={json.dumps(i,sort_keys=True):i for i in issues}
    evidence_pages=[{"sheet_id":s["id"],"source_sha256":pages[s["id"]]["source_sha256"],"run_id":pages[s["id"]]["_owner_run"],"page":pages[s["id"]]["_owner_page"]} for s in working["sheets"] if s["id"] in pages]
    working["automation"]={"run_id":job["id"],"software":VERSION,"state":"REVIEW_DRAFT",
        'processor':progress.get('processor','hosting'),'remote_transport':progress.get('remote_transport',[]),
        "application_release":api.BUILD_ID,"recognition_profile":"explicit-point-labels-v1" if proposals else "graphical-flanges-v1" if features else "general-review-v1",
        "input_sha256":sorted({s["sha256"] for s in working["sheets"]}),
        "issues":[dict(v,severity=v.get("severity","critical"),message=v.get("message",v["code"].replace("_"," ").capitalize())) for v in dedup.values()],
        "proposals":proposals,"graph_proposals":graphs,"feature_proposals":features,"inventory_ledger":inventory_ledger,
        "continuation_candidates":continuation_candidates,"continuation_pairs":candidate_matches(continuation_candidates,working['sheets']),
        "evidence_run":progress.get("evidence_run",job["id"]),"catalog_versions":progress["catalog_versions"],
        "route_selections":p.get("automation",{}).get("route_selections",[]),
        "evidence_pages":evidence_pages,
        "coverage":{"pages":len(pages),"material_rows":len(new_materials),"proposed_points":len(proposals),"graphical_features":len(features),"accepted_points":sum(n.get("verification")=="reviewed" and n.get('station_mm') is not None for n in working["nodes"]),"ocr_pages":sum(bool(page.get('ocr_used')) for page in pages.values())}}
    if working.get('source_review',{}).get('prepared'):
        from packages.physical.source_review import prepare_source_points
        prepare_source_points(working)
    if len(working["materials"])!=len(p["materials"]):working["materials_reviewed"]=False
    if old_layout!=[(s.get("axis"),s.get("table")) for s in working["sheets"]]:working["layout_reviewed"]=False
    with api.db() as conn:
        conn.execute("BEGIN IMMEDIATE");fenced(conn,job)
        current=api.project_read(job["project_id"],actor,conn)
        if current["version"]!=expected:raise RuntimeError("PROJECT_CHANGED")
        commit_project(api,conn,job,working,"Prepared automated evidence and engineering proposals",preserve_status=bool(json.loads(job["options"]).get("cached_from")))
    progress.update(revision=working["version"],coverage=working["automation"]["coverage"],exceptions=len(working["automation"]["issues"]),evidence_pages=evidence_pages,pages=len(working["sheets"]))
    advance(api,job,progress,"export")


def publish_export(api,project,actor,job=None):
    """Render privately; transactionally publish a single revision/purpose key."""
    with api.db() as conn:
        existing=conn.execute("SELECT * FROM artifacts WHERE project_id=? AND revision=? ORDER BY created LIMIT 1",(project["id"],project["version"])).fetchone()
        if existing:return dict(existing)
    artifact_id=api.uid();directory=api.DATA/"exports";directory.mkdir(exist_ok=True,mode=0o700)
    staged=directory/f"{artifact_id}.staged"
    project["issues"]=validate(project)
    published=False
    try:
        count=export_bundle(project,lambda sid:api.DATA/"sources"/f"{sid}.pdf",staged)
        if project.get("automation"):
            import zipfile
            with zipfile.ZipFile(staged,"a",zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("automation-report.json",json.dumps(project["automation"],indent=2))
                archive.writestr("source-manifest.json",json.dumps([{"sheet_id":s["id"],"sha256":s["sha256"],"page_index":s["page_index"]} for s in project["sheets"]],indent=2))
                archive.writestr("revision-report.json",json.dumps(project.get("revision_changes",[]),indent=2))
                from packages.workbooks.csv_export import csv_bundle
                from packages.workbooks.caesar_neutral import assess,neutral_file
                import io
                with zipfile.ZipFile(io.BytesIO(csv_bundle(project))) as csv_files:
                    for entry in csv_files.infolist():archive.writestr('csv/'+entry.filename,csv_files.read(entry))
                native_status=assess(project)
                if native_status['available']:
                    try:archive.writestr('caesar-import-candidate.cii',neutral_file(project))
                    except ValueError as error:native_status.update(available=False,missing=[str(error)])
                archive.writestr('native-export-status.json',json.dumps(native_status,indent=2))
                archive.writestr("evidence-index.json",json.dumps(project["automation"].get("evidence_pages",[]),indent=2))
                required_shas={s["sha256"] for s in project["sheets"]}|{m.get("source_sha256") for m in project["materials"]}|{n.get("source_sha256") for n in project["nodes"]}
                with api.db() as conn:
                    for row in conn.execute("SELECT id,sha,progress FROM pipeline_runs WHERE project_id=? ORDER BY created DESC",(project["id"],)):
                        if row["sha"] not in required_shas:continue
                        state=json.loads(row["progress"]);owner=state.get("evidence_run",row["id"])
                        for i,sheet_id in enumerate(state.get("sheets",[])):
                            name=f"evidence/{sheet_id}/{owner}-{i}.json";path=page_path(api,owner,i)
                            if name not in archive.namelist() and path.exists() and any(s["id"]==sheet_id for s in project["sheets"]):archive.writestr(name,path.read_bytes())
        with api.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if job is not None:fenced(conn,job)
            current=api.project_read(project["id"],actor,conn)
            if current["version"]!=project["version"]:raise RuntimeError("PROJECT_CHANGED")
            existing=conn.execute("SELECT * FROM artifacts WHERE project_id=? AND revision=? ORDER BY created LIMIT 1",(project["id"],project["version"])).fetchone()
            if existing:return dict(existing)
            record={"id":artifact_id,"project_id":project["id"],"revision":project["version"],"filename":f"caesar-review-r{project['version']}.zip","created":api.now(),"count":count}
            conn.execute("INSERT INTO artifact_keys VALUES (?,?,?,?)",(project["id"],project["version"],"draft",artifact_id))
            os.replace(staged,directory/f"{artifact_id}.zip")
            conn.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?)",tuple(record.values()))
            api.audit(conn,project["id"],actor["name"],"Automatically generated engineering review draft")
        published=True
        diag.emit(api.DATA,"pdf.export.published",artifact_id=artifact_id,revision=project["version"],annotations=count)
        return record
    finally:
        staged.unlink(missing_ok=True)
        if not published:(directory/f"{artifact_id}.zip").unlink(missing_ok=True)


def export(api,job,progress):
    with api.db() as conn:
        actor=actor_for(api,job,conn);p=api.project_read(job["project_id"],actor,conn)
    if p["version"]!=job["revision"]:raise RuntimeError("PROJECT_CHANGED")
    with diag.stage(api.DATA,"pipeline.export",run_id=job["id"]):artifact=publish_export(api,p,actor,job=job)
    progress["artifact"]=artifact
    advance(api,job,progress,"export","DONE")


def drain_outbox(api):
    with api.db() as conn:
        event=conn.execute("SELECT * FROM pipeline_outbox ORDER BY created LIMIT 1").fetchone()
        if not event:return
        actor=conn.execute("SELECT * FROM users WHERE id=?",(event["actor"],)).fetchone()
        row=conn.execute("SELECT * FROM pipeline_runs WHERE project_id=? AND stage IN ('compose','export') ORDER BY created DESC LIMIT 1",(event["project_id"],)).fetchone()
        p=api.project_read(event["project_id"],dict(actor),conn) if actor else None
        if not row and conn.execute("SELECT 1 FROM pipeline_runs WHERE project_id=? AND state NOT IN ('DONE','FAILED','CANCELLED','SUPERSEDED')",(event["project_id"],)).fetchone():return
    if p and p["version"]==event["revision"] and row:
        enqueue(api,p,dict(actor),row["source_id"],row["sha"],row["filename"],cached=row["id"])
    with api.db() as conn:conn.execute("DELETE FROM pipeline_outbox WHERE project_id=? AND revision=?",(event["project_id"],event["revision"]))


def process_one(api):
    if (api.DATA/"updates/maintenance.json").exists():return False
    drain_outbox(api)
    job=claim(api)
    if not job:return False
    token=diag.CONTEXT.set({"actor_id":job["actor"],"tenant":job["tenant"],"scope":{"path_params":{"project_id":job["project_id"]}}})
    try:
        diag.emit(api.DATA,"pipeline.stage.started",run_id=job["id"],stage=job["stage"],attempt=job["fence"])
        globals()[job["stage"]](api,job,json.loads(job["progress"]))
        diag.emit(api.DATA,"pipeline.stage.completed",run_id=job["id"],stage=job["stage"])
    except Exception as error:
        diag.exception(api.DATA,"pipeline.stage.failed",error,run_id=job["id"],stage=job["stage"])
        from services.api.remote_pages import RemoteFailure
        safe_remote = isinstance(error, (RemoteFailure, WorkerUnavailable)) and re.fullmatch(r'[A-Z0-9_]{1,100}', str(error))
        code=str(error) if safe_remote or str(error) in {"PROJECT_CHANGED","SOURCE_ALREADY_ACTIVE","STALE_ATTEMPT","REVISION_TARGET_CHANGED","SOURCE_HASH_MISMATCH","PARSER_ISOLATION_UNAVAILABLE","DOCUMENT_PROCESSING_FAILED","AUTHOR_PERMISSION_REVOKED"} else type(error).__name__
        state="SUPERSEDED" if code in ("PROJECT_CHANGED","SOURCE_ALREADY_ACTIVE","REVISION_TARGET_CHANGED") else "WAITING_WORKER" if isinstance(error,WorkerUnavailable) else "RETRY_WAIT" if isinstance(error,(OSError,TimeoutError,sqlite3.OperationalError)) and job["attempts"]<3 else "FAILED"
        with api.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:fenced(conn,job)
            except RuntimeError:return True
            conn.execute("UPDATE pipeline_runs SET state=?,error=?,lease=0,next_at=?,updated=? WHERE id=?",(state,code,time.time()+(60 if state=="WAITING_WORKER" else 15*job["attempts"]),time.time(),job["id"]))
            events(conn,job["id"],job["stage"],state,error_code=code)
    finally:diag.CONTEXT.reset(token)
    return True


def install(api):
    def operator(actor=Depends(api.user)):
        if actor["role"]!="admin" or (not api.LOCAL_DEMO and actor["id"]!="admin"):raise HTTPException(403,"Hosting administrator access required.")
        return actor
    class WorkerPolicy(BaseModel):
        mode:str=Field(pattern=r"^(isolated|bounded_pilot)$")
    class RerunInput(BaseModel):
        version:int=Field(ge=1)
        reextract:bool=False
    class RouteSelection(BaseModel):
        version:int=Field(ge=1)
        sheet_id:str
        start:int=Field(ge=0,le=1999)
        end:int=Field(ge=0,le=1999)

    @api.app.post("/api/v1/projects/{project_id}/pipeline/route")
    def select_route(project_id:str,body:RouteSelection,actor=Depends(api.editor)):
        def update(p):
            graph=next((g for g in p.get("automation",{}).get("graph_proposals",[]) if g["sheet_id"]==body.sheet_id),None)
            if not graph:raise HTTPException(409,"Source graph is not available yet.")
            sheet=api.sheet_for(p,body.sheet_id)
            if any(n["line_id"]==sheet["line_id"] and not n.get("graph_proposal") for n in p["nodes"]):
                raise HTTPException(409,"An existing reviewed/explicit route needs reconciliation before replacing its ordering.")
            try:nodes,warnings=propose_routes(graph,body.start,body.end,body.sheet_id,sheet["line_id"])
            except ValueError as error:raise HTTPException(422,str(error))
            existing={n["id"]:n for n in p["nodes"]}
            # Retain saved engineering/graphic corrections on corresponding IDs.
            for node in nodes:
                old=existing.get(node["id"])
                if old and old.get("verification")=="reviewed":
                    node.update({k:deepcopy(old[k]) for k in ("station_mm","dimension_input","evidence","instances","verification") if k in old})
            p["nodes"]=[n for n in p["nodes"] if n["line_id"]!=sheet["line_id"]]+nodes
            p["automation"].setdefault("route_selections",[]).append({"sheet_id":sheet["id"],"start":body.start,"end":body.end,"selected_by":actor["id"],"source_sha256":sheet["sha256"]})
            p["automation"]["issues"]=[i for i in p["automation"]["issues"] if not(i.get("sheet_id")==sheet["id"] and i["code"]=="PHYSICAL_ROUTE_REVIEW_REQUIRED")]+[{**i,"severity":"critical","message":i["code"].replace('_',' ').capitalize()} for i in warnings]
            p["layout_reviewed"]=False
        return api.change(project_id,body.version,actor,"Selected main route from source graphical candidates",update)

    @api.app.post("/api/v1/system/pipeline/config")
    def configure(body:WorkerPolicy,actor=Depends(operator)):
        write(api.DATA/"pipeline/config.json",{"mode":body.mode,"enabled":True})
        result={"mode":body.mode,"runner":"existing-service"}
        if not api.LOCAL_DEMO:
            import subprocess,sys
            command=[sys.executable,str(api.ROOT/"scripts/enable_pipeline.py")]
            if body.mode=="bounded_pilot":command.append("--bounded-pilot")
            completed=subprocess.run(command,capture_output=True,text=True,timeout=20)
            if completed.returncode:raise HTTPException(409,"Runner configuration could not complete. Use the account-level setup guide and private provider logs.")
            result["runner"]="scheduled"
        diag.emit(api.DATA,"pipeline.policy.changed",mode=body.mode,actor_id=actor["id"])
        with api.db() as conn:conn.execute("UPDATE pipeline_runs SET next_at=0 WHERE state='WAITING_WORKER'")
        return result

    @api.app.post('/api/v1/system/pipeline/ocr')
    def setup_ocr(actor=Depends(operator)):
        from services.api.ocr_setup import queue
        value=queue(api.DATA)
        diag.emit(api.DATA,'pipeline.ocr_setup.requested',actor_id=actor['id'],state=value['state'])
        return value

    @api.app.post("/api/v1/projects/{project_id}/intake",status_code=202)
    async def intake(project_id:str,request:Request,version:int=Query(ge=1),replace_source_id:str|None=None,actor=Depends(api.editor)):
        with api.db() as conn:
            p=api.project_read(project_id,actor,conn)
        if p["version"]!=version:raise HTTPException(409,"Project changed. Reload before uploading.")
        if replace_source_id and not any(s["source_id"]==replace_source_id for s in p["sheets"]):raise HTTPException(404,"Active revision source not found.")
        if request.headers.get("content-type","").split(";")[0]!="application/pdf":raise HTTPException(415,"Upload a PDF file.")
        from urllib.parse import unquote
        filename=Path(unquote(request.headers.get("x-filename","drawing.pdf"))).name[:200]
        if not filename.lower().endswith(".pdf"):raise HTTPException(415,"Upload a PDF file.")
        source_id=api.uid();path=api.DATA/"sources"/f"{source_id}.pdf";size=0;digest=hashlib.sha256();keep=False
        try:
            with path.open("xb") as stream:
                os.chmod(path,0o600)
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>30*1024**2:raise HTTPException(413,"PDF exceeds the 30 MB limit.")
                    digest.update(chunk);stream.write(chunk)
            with path.open("rb") as stream:
                if stream.read(5)!=b"%PDF-":raise HTTPException(415,"File signature is not PDF.")
            sha=digest.hexdigest()
            with api.db() as conn:
                candidates=conn.execute("SELECT * FROM pipeline_runs WHERE project_id=? AND sha=? AND state NOT IN ('FAILED','CANCELLED','SUPERSEDED') ORDER BY created DESC",(project_id,sha)).fetchall()
                existing=next((r for r in candidates if json.loads(r["options"]).get("replace_source_id")==replace_source_id and (r["state"]!="DONE" or any(s["source_id"]==r["source_id"] for s in p["sheets"]))),None)
            if existing:return public(existing)
            run=enqueue(api,p,actor,source_id,sha,filename,replace_source_id)
            with api.db() as conn:owned=conn.execute("SELECT source_id FROM pipeline_runs WHERE id=?",(run["id"],)).fetchone()
            keep=owned["source_id"]==source_id
            return run
        finally:
            if not keep:path.unlink(missing_ok=True)

    @api.app.get("/api/v1/projects/{project_id}/pipeline")
    def runs(project_id:str,actor=Depends(api.user)):
        with api.db() as conn:
            api.project_read(project_id,actor,conn)
            rows=conn.execute("SELECT * FROM pipeline_runs WHERE project_id=? ORDER BY created DESC LIMIT 20",(project_id,)).fetchall()
            last=api.DATA/"pipeline/heartbeat.json"
            runner=json.loads(last.read_text()) if last.exists() else {}
        from services.api.ocr_setup import status
        return {"runs":[public(row) for row in rows],"worker":{"recent":runner.get("at",0)>time.time()-180,"at":runner.get("at"),"executor":runner.get("executor","not-configured")},'ocr_setup':status(api.DATA)}

    @api.app.get("/api/v1/projects/{project_id}/pipeline/{run_id}")
    def detail(project_id:str,run_id:str,actor=Depends(api.user)):
        with api.db() as conn:
            api.project_read(project_id,actor,conn)
            row=conn.execute("SELECT * FROM pipeline_runs WHERE id=? AND project_id=?",(run_id,project_id)).fetchone()
            if not row:raise HTTPException(404,"Drawing job not found.")
            entries=[dict(e) for e in conn.execute("SELECT stage,state,at,details FROM pipeline_events WHERE run_id=? ORDER BY id",(run_id,))]
        return {**public(row),"events":entries}

    @api.app.post("/api/v1/projects/{project_id}/pipeline/{run_id}/cancel")
    def cancel(project_id:str,run_id:str,actor=Depends(api.editor)):
        with api.db() as conn:
            api.project_read(project_id,actor,conn)
            found=conn.execute("UPDATE pipeline_runs SET state='CANCELLED',fence=fence+1,updated=? WHERE id=? AND project_id=? AND state NOT IN ('DONE','FAILED','SUPERSEDED','CANCELLED')",(time.time(),run_id,project_id)).rowcount
            if not found:raise HTTPException(409,"Job is no longer active.")
        return {"ok":True}

    @api.app.post("/api/v1/projects/{project_id}/pipeline/{run_id}/retry")
    def retry(project_id:str,run_id:str,actor=Depends(api.editor)):
        with api.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            p=api.project_read(project_id,actor,conn)
            row=conn.execute("SELECT * FROM pipeline_runs WHERE id=? AND project_id=?",(run_id,project_id)).fetchone()
            if not row or row["state"] not in ('FAILED','WAITING_WORKER'):raise HTTPException(409,"Only a failed or waiting job can be retried.")
            if row["revision"] is not None and p["version"]!=row["revision"] and row["stage"] in ('compose','export'):raise HTTPException(409,"The project changed. Refresh the draft using the retained extraction instead.")
            conn.execute("UPDATE pipeline_runs SET state='QUEUED',attempts=0,next_at=0,fence=fence+1,error=NULL,actor=?,updated=? WHERE id=?",(actor['id'],time.time(),run_id))
            from services.api.remote_pages import retry as retry_remote_pages
            retry_remote_pages(api, conn, run_id)
            events(conn,run_id,row["stage"],"RETRY_REQUESTED")
        return {"ok":True}

    @api.app.get("/api/v1/projects/{project_id}/pipeline/{run_id}/evidence/{page}")
    def evidence(project_id:str,run_id:str,page:int,actor=Depends(api.user)):
        with api.db() as conn:
            api.project_read(project_id,actor,conn)
            row=conn.execute("SELECT * FROM pipeline_runs WHERE id=? AND project_id=?",(run_id,project_id)).fetchone()
            if not row:raise HTTPException(404,"Drawing job not found.")
        progress=json.loads(row["progress"])
        mapping=progress.get("evidence_pages")
        if not 0<=page<(len(mapping) if mapping is not None else progress["pages"]):raise HTTPException(404,"Evidence page not found.")
        path=page_path(api,mapping[page]["run_id"],mapping[page]["page"]) if mapping is not None else page_path(api,progress.get("evidence_run",run_id),page)
        if not path.exists():raise HTTPException(409,"Evidence page is still processing.")
        return json.loads(path.read_text())

    @api.app.post("/api/v1/projects/{project_id}/pipeline/rerun")
    def rerun(project_id:str,body:RerunInput,actor=Depends(api.editor)):
        with api.db() as conn:
            p=api.project_read(project_id,actor,conn)
            if p["version"]!=body.version:raise HTTPException(409,"Project changed. Reload first.")
            row=conn.execute("SELECT * FROM pipeline_runs WHERE project_id=? AND stage IN ('compose','export') ORDER BY created DESC LIMIT 1",(project_id,)).fetchone()
        if not row:raise HTTPException(409,"No completed extraction is available to reuse.")
        return enqueue(api,p,actor,row["source_id"],row["sha"],row["filename"],cached=None if body.reextract else row["id"])
