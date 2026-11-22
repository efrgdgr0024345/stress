"""Explicit, scoped engineering reviews and immutable independent approvals."""
from copy import deepcopy
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import tempfile
import time
import zipfile
from fastapi import Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from packages.reviews import digest,scopes,issues,snapshot_hash
from packages.engineering import validate
from services.api import account_security as security


def schema(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS review_signoffs (
      id TEXT PRIMARY KEY,project_id TEXT,tenant TEXT,scope TEXT,content_sha TEXT,
      actor TEXT,created TEXT,data TEXT,UNIQUE(project_id,scope,content_sha,actor));
    CREATE TABLE IF NOT EXISTS project_approvals (
      id TEXT PRIMARY KEY,project_id TEXT,tenant TEXT,source_revision INTEGER,
      actor TEXT,level TEXT,created TEXT,data TEXT);
    CREATE TABLE IF NOT EXISTS review_qualifications (
      id TEXT PRIMARY KEY,project_id TEXT,tenant TEXT,kind TEXT,content_sha TEXT,
      actor TEXT,created TEXT,data TEXT);
    ''')


def signing_key(api):
    path=api.DATA/'security/approval-key'
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink() or (path.exists() and (path.stat().st_mode&0o077 or path.stat().st_size!=32)):
        raise HTTPException(503,'Review signing key requires operator attention.')
    if not path.exists():
        with api.db() as conn:
            used=sum(conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('review_signoffs','project_approvals','review_qualifications'))
        if used:raise HTTPException(503,'Restore the original review signing key from the private backup.')
        fd,temporary=tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(secrets.token_bytes(32));stream.flush();os.fsync(stream.fileno())
            try:os.link(temporary,path)
            except FileExistsError:pass
        finally:os.unlink(temporary)
    return path.read_bytes()


def signed(api,data):
    key=signing_key(api)
    return {**data,'signature_algorithm':'HMAC-SHA256',
            'signing_key_id':hashlib.sha256(key).hexdigest()[:16],
            'signature':hmac.new(key,json.dumps(data,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()}


def authentic(api,data):
    core={k:v for k,v in data.items() if k not in ('signature','signature_algorithm','signing_key_id')}
    expected=signed(api,core)
    return all(secrets.compare_digest(expected[k],str(data.get(k,''))) for k in ('signature','signature_algorithm','signing_key_id'))


def file_sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def checked_packet(api,data):
    receipt=data['receipt'];target=api.DATA/'approvals'/f"{receipt['id']}.zip"
    proof=data.get('packet',{})
    if (not authentic(api,receipt) or snapshot_hash(data['snapshot'])!=receipt['project_sha256'] or
        data['snapshot'].get('status')!=receipt['level'] or data['snapshot'].get('review_approval')!=receipt or
        not authentic(api,proof) or proof.get('approval_id')!=receipt['id'] or
        not target.is_file() or target.is_symlink() or file_sha(target)!=proof.get('sha256')):
        raise HTTPException(409,'Signed project issue integrity check failed.')
    return target


def processing(conn,project):
    return {r['source_id'] for r in conn.execute("SELECT source_id FROM pipeline_runs WHERE project_id=? AND state NOT IN ('DONE','FAILED','CANCELLED','SUPERSEDED')",(project,))}


def current_qualifications(api,conn,p):
    result=[];sha=snapshot_hash(p)
    for row in conn.execute('SELECT * FROM review_qualifications WHERE project_id=? AND content_sha=?',(p['id'],sha)):
        value=json.loads(row['data'])
        if (not authentic(api,value) or value.get('project_id')!=p['id'] or value.get('project_sha256')!=sha or
            value.get('kind')!=row['kind'] or value.get('actor_id')!=row['actor']):
            raise HTTPException(409,'Qualification integrity check failed.')
        result.append(value)
    return result


def current_reviews(api,conn,p):
    result=scopes(p,processing(conn,p['id']))
    found=[{**dict(r),'data':json.loads(r['data'])} for r in conn.execute('SELECT * FROM review_signoffs WHERE project_id=? ORDER BY created DESC',(p['id'],))]
    people={r['id']:dict(r) for r in conn.execute('SELECT id,name,role FROM users')}
    for scope in result:
        match=next((r for r in found if r['scope']==scope['key'] and r['content_sha']==scope['sha256'] and
                    r['actor'] in people and people[r['actor']]['role'] in ('admin','engineer','reviewer') and security.active(conn,r['actor'])),None)
        if match:
            value=match['data']
            if (not authentic(api,value) or value.get('project_id')!=p['id'] or value.get('scope')!=scope['key'] or
                value.get('actor_id')!=match['actor'] or value.get('content_sha256')!=scope['sha256'] or
                digest(value.get('scope_snapshot'))!=scope['sha256']):
                raise HTTPException(409,'Review signature integrity check failed.')
        scope['review']=match['data'] if match else None
        scope['state']='SIGNED_WITH_EXCEPTIONS' if match and scope['blocking'] else 'SIGNED' if match else 'STALE' if any(r['scope']==scope['key'] for r in found) else 'WAITING_FOR_PROCESSING' if not scope['ready'] else 'PENDING_REVIEW'
    return result


def scope_public(value):
    return {k:v for k,v in value.items() if k!='payload'}


def commit_reviewed_data(api,conn,p,actor,action):
    p['version']+=1;p['updated']=api.now();p['status']='DRAFT';p.pop('review_approval',None)
    p['contributors']=sorted(set(p.get('contributors',[]))|{actor['id']})
    conn.execute('UPDATE projects SET version=?,data=? WHERE id=?',(p['version'],json.dumps(p),p['id']))
    conn.execute('INSERT INTO revisions VALUES (?,?,?)',(p['id'],p['version'],json.dumps(p)))
    if p.get('automation',{}).get('run_id'):
        conn.execute('INSERT OR IGNORE INTO pipeline_outbox VALUES (?,?,?,?)',(p['id'],p['version'],actor['id'],time.time()))
    api.audit(conn,p['id'],actor['name'],action)


def install(api):
    class PartReview(BaseModel):
        model_config=ConfigDict(extra='forbid')
        version:int=Field(ge=1)
        scope:str=Field(min_length=3,max_length=300)
        reason:str=Field(min_length=10,max_length=3000)
        acknowledge:list[str]=Field(default_factory=list,max_length=100)
        confirmed:Literal[True]
    class FinalReview(BaseModel):
        model_config=ConfigDict(extra='forbid')
        version:int=Field(ge=1)
        level:Literal['ENGINEERING_REVIEW','VERIFIED_FOR_MODELLING']='ENGINEERING_REVIEW'
        reason:str=Field(min_length=20,max_length=3000)
        acknowledge:list[str]=Field(default_factory=list,max_length=20000)
        code:str|None=Field(default=None,max_length=80)
        confirmed:Literal[True]
    class Qualification(BaseModel):
        model_config=ConfigDict(extra='forbid')
        version:int=Field(ge=1)
        kind:Literal['PDF_EDITOR','CAESAR_ROUNDTRIP']
        artifact_id:str=Field(pattern=r'^[a-f0-9-]{36}$')
        application:str=Field(min_length=2,max_length=100)
        application_version:str=Field(min_length=1,max_length=100)
        evidence:str=Field(min_length=30,max_length=4000)
        passed:Literal[True]
        code:str|None=Field(default=None,max_length=80)

    def lead(actor=Depends(api.user)):
        if actor['role'] not in ('admin','reviewer'):raise HTTPException(403,'Independent reviewer permission required.')
        return actor

    @api.app.get('/api/v1/projects/{project_id}/reviews')
    def get(project_id:str,actor=Depends(api.user)):
        with api.db() as conn:
            p=api.project_read(project_id,actor,conn)
            values=current_reviews(api,conn,p)
            history=[json.loads(r['data'])['receipt'] for r in conn.execute('SELECT data FROM project_approvals WHERE project_id=? ORDER BY created DESC',(project_id,))]
            qa=[json.loads(r['data']) for r in conn.execute('SELECT data FROM review_qualifications WHERE project_id=? ORDER BY created DESC',(project_id,))]
            pending=bool(processing(conn,project_id) or conn.execute('SELECT 1 FROM pipeline_outbox WHERE project_id=?',(project_id,)).fetchone())
        return {'revision':p['version'],'scopes':[scope_public(v) for v in values],
                'issues':issues(p),'processing':pending,'approvals':history,'qualifications':qa,
                'can_review':actor['role'] in ('admin','engineer'),'can_lead':actor['role'] in ('admin','reviewer'),
                'independent':actor['id'] not in ({v['review']['actor_id'] for v in values if v['review']}|set(p.get('contributors',[]))),
                'mfa':security.status(api,actor),'model_import_qualified':False}

    @api.app.post('/api/v1/projects/{project_id}/reviews/sign')
    def sign(project_id:str,body:PartReview,actor=Depends(api.editor)):
        # Initialize the key before acquiring the project transaction.
        signing_key(api)
        with api.LOCK,api.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            who=conn.execute('SELECT role FROM users WHERE id=? AND tenant=?',(actor['id'],actor['tenant'])).fetchone()
            if not who or who['role'] not in ('admin','engineer') or not security.active(conn,actor['id']):
                raise HTTPException(403,'Engineering editor access changed. Sign in again.')
            p=api.project_read(project_id,actor,conn)
            if p['version']!=body.version:raise HTTPException(409,'Project changed. Reload before signing.')
            scope=next((s for s in scopes(p,processing(conn,project_id)) if s['key']==body.scope),None)
            if not scope:raise HTTPException(404,'Review scope not found.')
            if not scope['ready']:raise HTTPException(409,'This part is still processing. Review available parts meanwhile.')
            original=deepcopy(p)
            existing=conn.execute('SELECT data FROM review_signoffs WHERE project_id=? AND scope=? AND content_sha=? AND actor=?',(project_id,body.scope,scope['sha256'],actor['id'])).fetchone()
            if existing:
                record=json.loads(existing['data'])
                if (not authentic(api,record) or record.get('project_id')!=project_id or record.get('scope')!=scope['key'] or
                    record.get('actor_id')!=actor['id'] or record.get('content_sha256')!=scope['sha256'] or
                    digest(record.get('scope_snapshot'))!=scope['sha256']):raise HTTPException(409,'Review signature integrity check failed.')
                return {'review':record,'project':{**p,'issues':validate(p)}}
            identity=body.scope.split(':',1)[1]
            if scope['kind']=='materials':
                for item in p['materials']:
                    if item['sheet_id']==identity:
                        item['verification']='reviewed'
                        item['review_acceptance']={'user_id':actor['id'],'at':api.now(),'evidence':body.reason}
            elif scope['kind']=='identity':
                sheet=next(s for s in p['sheets'] if s['id']==identity)
                if sheet.get('line_id') and sheet.get('printed_id'):sheet['identity_verified']=True
            scope=next(s for s in scopes(p,processing(conn,project_id)) if s['key']==body.scope)
            if set(scope['blocking'])-set(body.acknowledge):
                raise HTTPException(409,{'message':'Explicitly acknowledge remaining limitations or correct them before signing.','remaining':scope['blocking']})
            if p!=original:commit_reviewed_data(api,conn,p,actor,'Accepted a reviewed project section')
            existing=conn.execute('SELECT data FROM review_signoffs WHERE project_id=? AND scope=? AND content_sha=? AND actor=?',(project_id,body.scope,scope['sha256'],actor['id'])).fetchone()
            if existing:record=json.loads(existing['data'])
            else:
                record=signed(api,{'id':api.uid(),'project_id':project_id,'scope':body.scope,
                    'content_sha256':scope['sha256'],'revision':p['version'],'actor_id':actor['id'],
                    'actor_name':actor['name'],'actor_role':actor['role'],'created':api.now(),
                    'reason':body.reason,'acknowledged':scope['blocking'],'scope_snapshot':scope['payload']})
                conn.execute('INSERT INTO review_signoffs VALUES (?,?,?,?,?,?,?,?)',(record['id'],project_id,actor['tenant'],body.scope,scope['sha256'],actor['id'],record['created'],json.dumps(record)))
                api.audit(conn,project_id,actor['name'],'Signed project section',body.scope)
            current=current_reviews(api,conn,p)
            flags={kind:bool([s for s in current if s['kind']==kind]) and all(s['review'] for s in current if s['kind']==kind) for kind in ('materials','layout')}
            changed=False
            for kind,flag in flags.items():
                if flag and not p.get(kind+'_reviewed'):p[kind+'_reviewed']=True;changed=True
            if changed:commit_reviewed_data(api,conn,p,actor,'Completed project review checklist sections')
        api.diag.emit(api.DATA,'review.section.signed',project_id=project_id,scope_kind=scope['kind'],review_id=record['id'],revision=p['version'],actor_id=actor['id'])
        return {'review':record,'project':{**p,'issues':validate(p)}}

    @api.app.post('/api/v1/projects/{project_id}/reviews/qualifications')
    def qualification(project_id:str,body:Qualification,request:Request,actor=Depends(lead)):
        security.require_recent(api,actor,request,body.code)
        with api.db() as conn:
            p=api.project_read(project_id,actor,conn)
            artifact=conn.execute('SELECT * FROM artifacts WHERE id=? AND project_id=?',(body.artifact_id,project_id)).fetchone()
        if p['version']!=body.version or not artifact or artifact['revision']!=p['version']:
            raise HTTPException(409,'Test evidence must identify an artifact of the current project revision.')
        with zipfile.ZipFile(api.DATA/'exports'/f"{body.artifact_id}.zip") as archive:
            filename='annotated-review.pdf' if body.kind=='PDF_EDITOR' else 'caesar-import-candidate.cii'
            if filename not in archive.namelist():raise HTTPException(409,'This artifact does not contain the output required for that test.')
            source_sha=hashlib.sha256(archive.read(filename)).hexdigest()
        record=signed(api,{'id':api.uid(),'project_id':project_id,'revision':p['version'],
            'project_sha256':snapshot_hash(p),
            'kind':body.kind,'artifact_id':body.artifact_id,'source_sha256':source_sha,
            'application':body.application,'application_version':body.application_version,
            'evidence':body.evidence,'passed':True,'method':'HUMAN_ATTESTATION',
            'actor_id':actor['id'],'actor_name':actor['name'],'created':api.now()})
        with api.db() as conn:
            conn.execute('INSERT INTO review_qualifications VALUES (?,?,?,?,?,?,?,?)',(record['id'],project_id,actor['tenant'],body.kind,snapshot_hash(p),actor['id'],record['created'],json.dumps(record)))
            api.audit(conn,project_id,actor['name'],'Recorded external application qualification',body.kind)
        return record

    @api.app.post('/api/v1/projects/{project_id}/reviews/approve')
    def approve(project_id:str,body:FinalReview,request:Request,actor=Depends(lead)):
        security.require_recent(api,actor,request,body.code)
        with api.db() as conn:
            p=api.project_read(project_id,actor,conn)
            previous=conn.execute('SELECT data FROM project_approvals WHERE project_id=? AND source_revision=? AND actor=? AND level=?',(project_id,body.version,actor['id'],body.level)).fetchone()
            if previous:
                data=json.loads(previous['data']);checked_packet(api,data)
                return {'approval':data['receipt'],'project':{**p,'issues':validate(p)}}
            if p['version']!=body.version:raise HTTPException(409,'Project changed. Reload before final review.')
            if not p['sheets']:raise HTTPException(409,'Register and review a source drawing first.')
            if processing(conn,project_id) or conn.execute('SELECT 1 FROM pipeline_outbox WHERE project_id=?',(project_id,)).fetchone():
                raise HTTPException(409,'Processing or draft refresh is still running. Section reviews can continue.')
            values=current_reviews(api,conn,p)
            if any(not v['review'] or not v['ready'] for v in values):raise HTTPException(409,'Every current project section requires an engineer sign-off.')
            preparers={v['review']['actor_id'] for v in values}|set(p.get('contributors',[]))
            if actor['id'] in preparers:raise HTTPException(409,'An independent reviewer must approve a project they did not prepare or sign as engineer.')
            outstanding=issues(p)
            qa_records=current_qualifications(api,conn,p)
            if set(i['id'] for i in outstanding)-set(body.acknowledge):
                raise HTTPException(409,'Acknowledge every listed outstanding issue for an engineering-review issue.')
            if body.level=='VERIFIED_FOR_MODELLING':
                if any(i['severity']=='critical' for i in outstanding) or any(v['blocking'] for v in values):
                    raise HTTPException(409,'Critical source/model limitations prevent verified-for-modelling approval.')
                # External application attestations remain explicit human acts.
                qa={r['kind']:r for r in qa_records}
                if not {'PDF_EDITOR','CAESAR_ROUNDTRIP'}<=set(qa):
                    raise HTTPException(409,'Current PDF-editor and CAESAR application round-trip qualification are required.')
                if any(not authentic(api,v) for v in qa.values()):raise HTTPException(409,'Qualification integrity check failed.')
                from packages.workbooks import readiness
                if not readiness(p)['direct_import_ready']:
                    raise HTTPException(409,'The installed CAESAR export profile is not qualified for verified modelling. An engineering-review issue remains available.')
        from services.api.pipeline import publish_export
        try:artifact=publish_export(api,deepcopy(p),actor)
        except RuntimeError as error:
            if str(error)=='PROJECT_CHANGED':raise HTTPException(409,'Project changed while preparing the signed issue.') from None
            raise
        record=signed(api,{'id':api.uid(),'project_id':project_id,'revision':p['version'],
            'project_sha256':snapshot_hash(p),'level':body.level,'actor_id':actor['id'],
            'actor_name':actor['name'],'actor_role':actor['role'],'created':api.now(),
            'reason':body.reason,'engineer_signoffs':[v['review']['id'] for v in values],
            'outstanding_issues':outstanding,'artifact_id':artifact['id'],
            'external_tests':[q['id'] for q in qa_records]})
        frozen=deepcopy(p);frozen['status']=body.level;frozen['review_approval']=record
        target=api.DATA/'approvals'/f"{record['id']}.zip"
        target.parent.mkdir(exist_ok=True,mode=0o700)
        source=api.DATA/'exports'/f"{artifact['id']}.zip"
        # Copy known generated entries, not untrusted archive paths or files.
        try:
            with zipfile.ZipFile(source) as old,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as new:
                for entry in old.infolist():new.writestr(entry,old.read(entry))
                new.writestr('approval-receipt.json',json.dumps(record,indent=2))
                new.writestr('approved-project-snapshot.json',json.dumps(frozen,indent=2))
                new.writestr('section-signoffs.json',json.dumps([v['review'] for v in values],indent=2))
                new.writestr('external-test-attestations.json',json.dumps(qa_records,indent=2))
            target.chmod(0o600)
            packet=signed(api,{'approval_id':record['id'],'sha256':file_sha(target)})
            with api.LOCK,api.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                latest=api.project_read(project_id,actor,conn)
                if latest['version']!=body.version or snapshot_hash(latest)!=record['project_sha256']:
                    raise HTTPException(409,'Project changed while preparing the signed issue. Review the latest draft.')
                who=conn.execute('SELECT role FROM users WHERE id=?',(actor['id'],)).fetchone()
                if not who or who['role'] not in ('admin','reviewer') or not security.active(conn,actor['id']):raise HTTPException(403,'Reviewer access changed during approval.')
                if processing(conn,project_id) or conn.execute('SELECT 1 FROM pipeline_outbox WHERE project_id=?',(project_id,)).fetchone():
                    raise HTTPException(409,'Processing restarted while preparing the signed issue.')
                current=current_reviews(api,conn,latest)
                if any(not v['review'] or not v['ready'] for v in current):raise HTTPException(409,'An engineer sign-off changed while preparing the signed issue.')
                conn.execute('INSERT INTO project_approvals VALUES (?,?,?,?,?,?,?,?)',(record['id'],project_id,actor['tenant'],p['version'],actor['id'],body.level,record['created'],json.dumps({'receipt':record,'snapshot':frozen,'packet':packet})))
                conn.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(frozen),project_id))
                api.audit(conn,project_id,actor['name'],'Approved immutable project issue',body.level+' · '+record['id'])
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        api.diag.emit(api.DATA,'review.project.approved',project_id=project_id,approval_id=record['id'],revision=p['version'],release_level=body.level,actor_id=actor['id'])
        return {'approval':record,'project':{**frozen,'issues':validate(frozen)}}

    @api.app.get('/api/v1/projects/{project_id}/reviews/approvals/{approval_id}/download')
    def download(project_id:str,approval_id:str,actor=Depends(api.user)):
        with api.db() as conn:
            api.project_read(project_id,actor,conn)
            found=conn.execute('SELECT data FROM project_approvals WHERE id=? AND project_id=? AND tenant=?',(approval_id,project_id,actor['tenant'])).fetchone()
        if not found:raise HTTPException(404,'Signed project issue not found.')
        data=json.loads(found['data'])
        if data['receipt'].get('project_id')!=project_id or data['receipt'].get('id')!=approval_id:raise HTTPException(409,'Signed issue identity mismatch.')
        return api.FileResponse(checked_packet(api,data),media_type='application/zip',filename=f"caesar-signed-r{data['receipt']['revision']}.zip")

    @api.app.get('/api/v1/projects/{project_id}/reviews/approvals/{approval_id}/verify')
    def verify_issue(project_id:str,approval_id:str,actor=Depends(api.user)):
        with api.db() as conn:
            api.project_read(project_id,actor,conn)
            found=conn.execute('SELECT data FROM project_approvals WHERE id=? AND project_id=? AND tenant=?',(approval_id,project_id,actor['tenant'])).fetchone()
        if not found:raise HTTPException(404,'Signed project issue not found.')
        data=json.loads(found['data'])
        if data['receipt'].get('project_id')!=project_id or data['receipt'].get('id')!=approval_id:raise HTTPException(409,'Signed issue identity mismatch.')
        checked_packet(api,data)
        return {'valid':True,'approval_id':approval_id,'revision':data['receipt']['revision'],
                'packet_sha256':data['packet']['sha256'],'method':'Private-server HMAC-SHA256 seal and SHA256 packet checksum'}
