"""Explicit hosting-owner workspace reset with a private recoverable snapshot.

Reference catalogs, genuine users, provider/update settings and paid-use counters
are retained. No untrusted archive is extracted and no shell command is run.
"""
import hashlib,json,os,re,secrets,sqlite3,time
from pathlib import Path
from typing import Literal
from fastapi import Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field
from services.api.updates import lock,pipeline_guard,write,read
from services.api import account_security

UUID=re.compile(r'^[a-f0-9-]{36}$')
PROJECT_TABLES=('projects','revisions','sources','artifacts','pipeline_runs','pipeline_outbox',
                'artifact_keys','review_signoffs','project_approvals','review_qualifications')


def plan(conn,tenant,data=None):
    projects=[dict(r) for r in conn.execute('SELECT * FROM projects WHERE tenant=? ORDER BY id',(tenant,))]
    ids={p['id'] for p in projects}
    rows={}
    for table in PROJECT_TABLES:
        field='id' if table in ('projects','revisions') else 'project_id'
        rows[table]=[dict(r) for r in conn.execute('SELECT * FROM '+table) if r[field] in ids]
    runs={r['id'] for r in rows['pipeline_runs']}
    rows['pipeline_events']=[dict(r) for r in conn.execute('SELECT * FROM pipeline_events') if r['run_id'] in runs]
    rows['remote_pages']=[dict(r) for r in conn.execute('SELECT * FROM remote_pages') if r['run_id'] in runs]
    rows['audit']=[dict(r) for r in conn.execute('SELECT * FROM audit') if r['project_id'] in ids]
    users=[dict(r) for r in conn.execute("SELECT * FROM users WHERE tenant=? AND email LIKE 'software-review-%@example.invalid' AND name LIKE 'Software QA %' AND id<>'admin'",(tenant,))]
    demo=read(Path(data)/'providers/digitalocean/demo.json') if data else {}
    prototype={k:demo.get(k) for k in ('id','state','project_id') if k in demo}
    # Only the selected workspace's demonstration is part of this reset.
    if prototype.get('project_id') not in ids:prototype={}
    core={'project_records':rows,'temporary_accounts':users,'prototype_demo':prototype}
    sha=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'sha256':sha,'rows':rows,'users':users,'prototype_demo':prototype,'counts':{
        'projects':len(projects),'source_files':len(rows['sources']),'exports':len(rows['artifacts']),
        'approved_issues':len(rows['project_approvals']),'processing_runs':len(runs),
        'temporary_accounts':len(users),'processing_demonstrations':int(bool(prototype))},
        'active':any(r['state'] not in ('DONE','FAILED','CANCELLED','SUPERSEDED') for r in rows['pipeline_runs']) or prototype.get('state') in ('queued','running','waiting')}


def paths(api,value):
    result=[]
    for table,folder,suffix in (('sources','sources','.pdf'),('artifacts','exports','.zip'),('project_approvals','approvals','.zip'),('pipeline_runs','pipeline','')):
        for row in value['rows'][table]:
            if not UUID.fullmatch(row['id']):raise HTTPException(409,'Legacy storage identity requires operator review before reset.')
            result.append(api.DATA/folder/(row['id']+suffix))
    for row in value['rows']['remote_pages']:
        if not UUID.fullmatch(row['id']):raise HTTPException(409,'Invalid remote evidence identity.')
        result.extend(api.DATA/'pipeline/remote-pages'/(row['id']+suffix) for suffix in ('.pdf','.json'))
    for user in value['users']:
        result.append(account_security.path(api,user['id']))
    demo=value.get('prototype_demo',{})
    if demo:
        if not UUID.fullmatch(demo.get('id','')):raise HTTPException(409,'Legacy demonstration storage requires operator review before reset.')
        result.extend((api.DATA/'providers/digitalocean/demo.json',api.DATA/'providers/digitalocean'/demo['id']))
    found=[]
    for path in result:
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p.is_relative_to(api.DATA)):
            raise HTTPException(409,'Private project storage must not use symlinks.')
        if path.exists():found.append(path)
    return found


def execute(api,actor,expected):
    directory=api.DATA/'updates';backup=None;moved=[];committed=False
    with lock(directory),pipeline_guard(directory) as idle,lock(api.DATA/'providers/digitalocean'):
        if not idle:raise HTTPException(409,'Let the processing/update worker finish before clearing the workspace.')
        if (directory/'maintenance.json').exists():raise HTTPException(409,'A maintenance operation is already active.')
        write(directory/'maintenance.json',{'active':True,'purpose':'workspace-reset'})
        try:
            with api.LOCK,api.db() as conn:
                conn.execute('BEGIN IMMEDIATE');value=plan(conn,actor['tenant'],api.DATA)
                if value['sha256']!=expected:raise HTTPException(409,'Workspace changed. Refresh the reset preview before clearing it.')
                if value['active']:raise HTTPException(409,'Finish or cancel pending drawing jobs before clearing their data.')
                targets=paths(api,value)
                root=api.DATA/'reset-backups';root.mkdir(exist_ok=True,mode=0o700)
                backup=root/(str(int(time.time()))+'-'+secrets.token_hex(6));backup.mkdir(mode=0o700)
                # A separate read connection can snapshot the committed state
                # while this connection holds the writer reservation.
                with api.db() as original,sqlite3.connect(backup/'database.sqlite3') as saved:original.backup(saved)
                (backup/'database.sqlite3').chmod(0o600)
                write(backup/'manifest.json',{'format':1,'tenant':actor['tenant'],'counts':value['counts'],
                    'project_ids':[r['id'] for r in value['rows']['projects']],
                    'temporary_account_ids':[u['id'] for u in value['users']],
                    'files':[p.relative_to(api.DATA).as_posix() for p in targets],
                    'retained':['administrator and genuine users','reference catalogs','provider and updater configuration','paid-use counters']})
                for path in targets:
                    target=backup/'files'/path.relative_to(api.DATA);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    os.replace(path,target);moved.append((path,target))
                projects=[r['id'] for r in value['rows']['projects']];runs=[r['id'] for r in value['rows']['pipeline_runs']]
                for uid in runs:
                    conn.execute('DELETE FROM pipeline_events WHERE run_id=?',(uid,));conn.execute('DELETE FROM remote_pages WHERE run_id=?',(uid,))
                for table in reversed(PROJECT_TABLES):
                    field='id' if table in ('projects','revisions') else 'project_id'
                    for uid in projects:conn.execute('DELETE FROM '+table+' WHERE '+field+'=?',(uid,))
                for uid in projects:conn.execute('DELETE FROM audit WHERE project_id=?',(uid,))
                for user in value['users']:
                    for table,field in (('sessions','user_id'),('session_assurance','user_id'),('account_state','user_id'),('mfa_accounts','user_id'),('mfa_limits','user_id'),('users','id')):
                        conn.execute('DELETE FROM '+table+' WHERE '+field+'=?',(user['id'],))
                api.audit(conn,'system:workspace',actor['name'],'Cleared project/test workspace with private backup',json.dumps(value['counts']))
                conn.commit()
                committed=True
                try:write(backup/'complete.json',{'completed':True,'at':api.now(),'backup_id':backup.name})
                except OSError as error:api.diag.exception(api.DATA,'workspace.reset.completion_marker_failed',error)
            api.diag.emit(api.DATA,'workspace.reset.completed',backup_id=backup.name,**value['counts'])
            return {'cleared':value['counts'],'backup_id':backup.name,'projects_remaining':0,
                    'retained':['administrator and genuine users','reference catalogs','provider and updater configuration','paid-use counters']}
        except BaseException:
            # Ordinary failures restore moved files; SQL rolls back on leaving
            # its connection context. A process kill needs the retained private
            # DB/files manifest for an operator-assisted recovery.
            if not committed:
                for original,saved in reversed(moved):
                    if saved.exists() and not original.exists():original.parent.mkdir(parents=True,exist_ok=True,mode=0o700);os.replace(saved,original)
            raise
        finally:(directory/'maintenance.json').unlink(missing_ok=True)


def install(api):
    def owner(actor=Depends(api.user)):
        if actor['role']!='admin' or (not api.LOCAL_DEMO and actor['id']!='admin'):
            raise HTTPException(403,'Hosting administrator access required.')
        return actor
    class Reset(BaseModel):
        model_config=ConfigDict(extra='forbid')
        plan_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
        confirmation:Literal['CLEAR PROJECT DATA']
        code:str|None=Field(default=None,max_length=80)

    @api.app.get('/api/v1/system/workspace-reset')
    def preview(actor=Depends(owner)):
        with api.db() as conn:value=plan(conn,actor['tenant'],api.DATA)
        return {'plan_sha256':value['sha256'],'counts':value['counts'],'processing':value['active'],
                'mfa':account_security.status(api,actor),'reference_catalogs_retained':True}

    @api.app.post('/api/v1/system/workspace-reset')
    def reset(body:Reset,request:Request,actor=Depends(owner)):
        if account_security.status(api,actor)['enabled']:account_security.require_recent(api,actor,request,body.code)
        return execute(api,actor,body.plan_sha256)
