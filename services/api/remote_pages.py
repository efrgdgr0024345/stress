"""Bounded per-page private transfers behind the unchanged project workflow."""
import base64
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import secrets
import time
from uuid import uuid4, uuid5, NAMESPACE_URL

from fastapi import HTTPException, Request
from services.api import diagnostics as diag, digitalocean as provider, remote_setup
from services.api.updates import read, write
from services.api.pipeline_executor import execute, WorkerUnavailable
from packages.automation.contracts import PageEvidence

MAX_PAGE = 30 * 1024**2
MAX_RESULT = 16 * 1024**2
MAX_RUN_EVIDENCE = 64 * 1024**2
ACTIVE = ('PREPARED', 'SUBMITTING', 'SUBMITTED', 'AMBIGUOUS')
TRANSIENT = {'REMOTE_SOURCE_TRANSFER_FAILED', 'REMOTE_PAGE_TRANSFER_FAILED', 'REMOTE_RESULT_DELIVERY_FAILED'}
ROOT_URL = 'https://easyai.com.au/stress/api/v1/worker/pages/'


class RemoteFailure(ValueError):
    pass


def schema(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS remote_pages (
      id TEXT PRIMARY KEY, run_id TEXT, tenant TEXT, page_index INTEGER,
      page_sha TEXT, source_sha TEXT, metadata TEXT, nonce TEXT, grant_hash TEXT,
      expires REAL, state TEXT, activation TEXT, attempts INTEGER DEFAULT 0,
      submitted REAL DEFAULT 0, deadline REAL DEFAULT 0, error TEXT, result_sha TEXT,
      source_reads INTEGER DEFAULT 0, result_bytes INTEGER DEFAULT 0,
      UNIQUE(run_id,page_index));
    CREATE TABLE IF NOT EXISTS remote_usage (bucket TEXT PRIMARY KEY, count INTEGER);
    ''')


def paths(api, identity):
    if not re.fullmatch(r'[a-f0-9-]{36}', identity):raise RemoteFailure('REMOTE_TASK_ID_INVALID')
    root = api.DATA / 'pipeline/remote-pages'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root / (identity + '.pdf'), root / (identity + '.json')


def key(api):
    path = remote_setup.directory(api.DATA) / 'grant-key'
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():raise RemoteFailure('REMOTE_GRANT_STORAGE_UNSAFE')
    if not path.exists():
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:stream.write(secrets.token_bytes(32))
        except FileExistsError:pass
    if path.stat().st_mode & 0o077 or path.stat().st_size != 32:
        raise RemoteFailure('REMOTE_GRANT_STORAGE_UNSAFE')
    return path.read_bytes()


def token(api, task):
    text = '|'.join(str(task[k]) for k in ('id', 'run_id', 'tenant', 'page_sha', 'nonce'))
    return base64.urlsafe_b64encode(hmac.new(key(api), text.encode(), hashlib.sha256).digest()).decode().rstrip('=')


def rows(api, run):
    with api.db() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM remote_pages WHERE run_id=? ORDER BY page_index', (run,))]


def reserve(api):
    """Reserve one billable submission before contacting the provider."""
    now = datetime.now(timezone.utc)
    buckets = [(now.strftime('day:%Y-%m-%d'), remote_setup.policy(api.DATA)['daily_limit'],
                (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()),
               (now.strftime('month:%Y-%m'), remote_setup.policy(api.DATA)['monthly_limit'],
                (now.replace(day=28, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=4)).replace(day=1).timestamp())]
    with api.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        for bucket, limit, reset in buckets:
            found = conn.execute('SELECT count FROM remote_usage WHERE bucket=?', (bucket,)).fetchone()
            if found and found['count'] >= limit:return reset
        for bucket, _, _ in buckets:
            conn.execute('INSERT INTO remote_usage VALUES (?,1) ON CONFLICT(bucket) DO UPDATE SET count=count+1', (bucket,))
    return None


def prepare(api, job, index):
    from services.api import pipeline
    source = api.DATA / 'sources' / f"{job['source_id']}.pdf"
    value = execute(source, 'slice', index, heartbeat=lambda: pipeline.heartbeat(api, job))
    if value.get('error'):raise RemoteFailure('REMOTE_PAGE_TRANSFER_LIMIT')
    if value.get('source_sha256') != job['sha'] or value.get('page_index') != index:
        raise RemoteFailure('REMOTE_SOURCE_IDENTITY_MISMATCH')
    with api.db() as conn:
        project = json.loads(conn.execute('SELECT data FROM projects WHERE id=? AND tenant=?', (job['project_id'], job['tenant'])).fetchone()['data'])
    sheet = next((s for s in project['sheets'] if s['source_id'] == job['source_id'] and s['page_index'] == index), None)
    if not sheet or any(value['metadata'].get(k) != sheet.get(k) for k in ('width', 'height', 'rotation', 'content_hash')):
        raise RemoteFailure('REMOTE_SPLIT_PAGE_GEOMETRY_MISMATCH')
    content = base64.b64decode(value['pdf_base64'], validate=True)
    if len(content) > MAX_PAGE or not content.startswith(b'%PDF-') or hashlib.sha256(content).hexdigest() != value['page_sha256']:
        raise RemoteFailure('REMOTE_PAGE_IDENTITY_MISMATCH')
    value['metadata']['transfer_bytes']=len(content)
    task = {'id': str(uuid4()), 'run_id': job['id'], 'tenant': job['tenant'], 'page_index': index,
            'page_sha': value['page_sha256'], 'source_sha': job['sha'], 'metadata': json.dumps(value['metadata']),
            'nonce': secrets.token_hex(16), 'expires': time.time() + 900, 'state': 'PREPARED',
            'activation': None, 'attempts': 0, 'submitted': 0, 'deadline': 0, 'error': None, 'result_sha': None}
    task['grant_hash'] = hashlib.sha256(token(api, task).encode()).hexdigest()
    path, _ = paths(api, task['id'])
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:stream.write(content)
    with api.db() as conn:
        conn.execute('BEGIN IMMEDIATE');pipeline.fenced(conn, job)
        columns = list(task)
        conn.execute('INSERT INTO remote_pages (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', [task[k] for k in columns])
    diag.emit(api.DATA, 'provider.page.prepared', run_id=job['id'], task_id=task['id'], page=index + 1,
              source_sha256=job['sha'], page_sha256=task['page_sha'], transfer_bytes=len(content))
    return task


def submit(api, job, task):
    from services.api import pipeline
    reset = reserve(api)
    if reset:return reset
    # Persist before submission. A source fetch records the actual activation,
    # allowing recovery even if the acknowledgement is lost.
    task.update(nonce=secrets.token_hex(16), expires=time.time() + 900)
    task['grant_hash'] = hashlib.sha256(token(api, task).encode()).hexdigest()
    with api.db() as conn:
        conn.execute('BEGIN IMMEDIATE');pipeline.fenced(conn, job)
        changed = conn.execute("UPDATE remote_pages SET state='SUBMITTING',attempts=attempts+1,submitted=?,deadline=?,nonce=?,grant_hash=?,expires=?,source_reads=0 WHERE id=? AND activation IS NULL AND state IN ('PREPARED','AMBIGUOUS')",
                     (time.time(), time.time() + 360, task['nonce'], task['grant_hash'], task['expires'], task['id'])).rowcount
        if not changed:return None
    url = ROOT_URL + task['id']
    event = {'source_url': url + '/source', 'result_url': url + '/result',
             'lease': token(api, task), 'request_id': task['id'], 'sha256': task['page_sha'], 'page': 0}
    try:
        response = remote_setup.call(api, remote_setup.ACTION + '?blocking=false', 'POST', event)
        identity = response.get('activationId', '')
        if not re.fullmatch(r'[a-f0-9]{32}', identity):raise provider.ProviderError('ACTIVATION_ID_INVALID')
        with api.db() as conn:
            conn.execute("UPDATE remote_pages SET state=CASE WHEN state IN ('RESULT_READY','DONE') THEN state ELSE 'SUBMITTED' END, activation=COALESCE(activation,?) WHERE id=?", (identity, task['id']))
        diag.emit(api.DATA, 'provider.page.submitted', run_id=job['id'], task_id=task['id'], page=task['page_index'] + 1, activation_id=identity)
    except provider.ProviderError as error:
        code = str(error)
        ambiguous = code in ('PROVIDER_CONNECTION_FAILED', 'PROVIDER_HTTP_429', 'PROVIDER_HTTP_500', 'PROVIDER_HTTP_502', 'PROVIDER_HTTP_503', 'PROVIDER_HTTP_504')
        with api.db() as conn:
            conn.execute("UPDATE remote_pages SET state=CASE WHEN activation IS NOT NULL THEN 'SUBMITTED' ELSE ? END,error=? WHERE id=? AND state NOT IN ('RESULT_READY','DONE')",
                         ('AMBIGUOUS' if ambiguous else 'FAILED', code, task['id']))
        if not ambiguous:raise RemoteFailure('REMOTE_' + code)
    return None


def validate_result(task, value):
    if not isinstance(value, dict) or set(value) != {'format','request_id','evidence','elapsed_ms','parser_peak_rss_kib'} or value.get('format') != 'caesar-remote-page-result-1' or value.get('request_id') != task['id']:
        raise RemoteFailure('REMOTE_RESULT_IDENTITY_MISMATCH')
    evidence = PageEvidence.model_validate({**value['evidence'], 'isolation': 'provider-function'}).model_dump(mode='json')
    expected = json.loads(task['metadata'])
    if evidence['source_sha256'] != task['page_sha'] or evidence['page_index'] != 0:
        raise RemoteFailure('REMOTE_RESULT_SOURCE_MISMATCH')
    if any(evidence[k] != expected[k] for k in ('width', 'height', 'rotation', 'content_hash')):
        raise RemoteFailure('REMOTE_RESULT_PAGE_GEOMETRY_MISMATCH')
    for key, limit in (('elapsed_ms', 300000), ('parser_peak_rss_kib', 2 * 1024**2)):
        if type(value.get(key)) is not int or not 0 <= value[key] <= limit:
            raise RemoteFailure('REMOTE_RESULT_METRICS_INVALID')
    return {**value, 'evidence': evidence}


def collect(api, job, task):
    from services.api import pipeline
    value = validate_result(task, read(paths(api, task['id'])[1]))
    evidence = value['evidence']
    evidence.update(source_sha256=job['sha'], page_index=task['page_index'])
    for word in evidence['words'] + evidence['uncertain_words']:
        word.pop('evidence_id', None)
        word['evidence_id'] = str(uuid5(NAMESPACE_URL, job['sha'] + f":{task['page_index']}:" + repr(word)))
    destination = pipeline.page_path(api, job['id'], task['page_index'])
    staged = destination.with_suffix('.remote-staged')
    write(staged, evidence)
    with api.db() as conn:
        conn.execute('BEGIN IMMEDIATE');pipeline.fenced(conn, job)
        os.replace(staged, destination)
        if task['state'] != 'DONE':
            pipeline.publish_page_review(api, conn, job, task['page_index'], evidence)
        metadata={**json.loads(task['metadata']),'ocr_used':evidence['ocr_used'],
                  'words':len(evidence['words']),'elapsed_ms':value['elapsed_ms'],
                  'parser_peak_rss_kib':value['parser_peak_rss_kib']}
        conn.execute("UPDATE remote_pages SET state='DONE',error=NULL,metadata=? WHERE id=?", (json.dumps(metadata),task['id']))
    for temporary in paths(api, task['id']):temporary.unlink(missing_ok=True)
    diag.emit(api.DATA, 'provider.project_page.completed', run_id=job['id'], task_id=task['id'],
              page=task['page_index'] + 1, words=len(evidence['words']), ocr_used=evidence['ocr_used'],
              elapsed_ms=value['elapsed_ms'], parser_peak_rss_kib=value['parser_peak_rss_kib'])


def recover(api, task):
    """Read-only recovery; never re-OCR an accepted successful page."""
    if task['activation']:
        response = remote_setup.call(api, '/activations/' + task['activation'], pending=True)
        if response is not None and response.get('response'):
            result = provider.find_result(response)
            if result and result.get('ok') and result.get('encoding') == 'gzip+base64':
                packed = base64.b64decode(result['evidence'], validate=True)
                with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:content = stream.read(MAX_RESULT + 1)
                if len(content) > MAX_RESULT:raise RemoteFailure('REMOTE_RESULT_LIMIT')
                value = validate_result(task, {'format': 'caesar-remote-page-result-1', 'request_id': task['id'],
                    'evidence': json.loads(content), 'elapsed_ms': result['elapsed_ms'], 'parser_peak_rss_kib': result['parser_peak_rss_kib']})
                size=len(json.dumps(value).encode())
                with api.db() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    used=conn.execute('SELECT COALESCE(SUM(result_bytes),0) FROM remote_pages WHERE run_id=?',(task['run_id'],)).fetchone()[0]
                    if used+size>MAX_RUN_EVIDENCE:raise RemoteFailure('REMOTE_EVIDENCE_BUDGET_REACHED')
                    write(paths(api, task['id'])[1], value)
                    conn.execute("UPDATE remote_pages SET state='RESULT_READY',result_bytes=? WHERE id=?", (size,task['id']))
                return
            # A successful callback was committed before provider completion.
            if result and result.get('delivery') == 'callback':return
            code = result.get('error') if isinstance(result, dict) else 'FUNCTION_FAILED'
            code = code if isinstance(code, str) and re.fullmatch(r'[A-Z0-9_]{1,80}', code) else 'FUNCTION_FAILED'
            with api.db() as conn:conn.execute("UPDATE remote_pages SET state='FAILED',error=? WHERE id=? AND state NOT IN ('RESULT_READY','DONE')", ('REMOTE_' + code, task['id']))
        elif time.time() > task['deadline']:
            with api.db() as conn:conn.execute("UPDATE remote_pages SET state='FAILED',error='REMOTE_FUNCTION_TIMEOUT' WHERE id=?", (task['id'],))
    elif task['state'] in ('SUBMITTING', 'AMBIGUOUS') and time.time() - task['submitted'] > 120:
        with api.db() as conn:
            if task['attempts'] >= remote_setup.policy(api.DATA)['attempt_limit']:
                conn.execute("UPDATE remote_pages SET state='FAILED',error='REMOTE_SUBMISSION_UNCERTAIN' WHERE id=? AND activation IS NULL", (task['id'],))
            else:conn.execute("UPDATE remote_pages SET state='AMBIGUOUS' WHERE id=? AND activation IS NULL", (task['id'],))


def step(api, job, progress):
    from services.api import pipeline
    if not remote_setup.ensure(api) or remote_setup.status(api.DATA).get('state') != 'ready':
        raise WorkerUnavailable(remote_setup.status(api.DATA).get('error') or 'REMOTE_WORKER_PREPARING')
    reset = None
    for task in rows(api, job['id']):
        if task['state'] == 'RESULT_READY':collect(api, job, task)
        elif task['state'] in ('SUBMITTING', 'SUBMITTED', 'AMBIGUOUS'):recover(api, task)
    tasks = rows(api, job['id'])
    for task in tasks:
        if task['state'] == 'FAILED' and task['error'] in TRANSIENT and task['attempts'] < remote_setup.policy(api.DATA)['attempt_limit']:
            with api.db() as conn:
                conn.execute("UPDATE remote_pages SET state='PREPARED',activation=NULL,error=NULL,source_reads=0 WHERE id=? AND state='FAILED'", (task['id'],))
            diag.emit(api.DATA, 'provider.page.retry_scheduled', run_id=job['id'], task_id=task['id'], page=task['page_index'] + 1, attempt=task['attempts'] + 1)
    tasks = rows(api, job['id'])
    failed = next((t for t in tasks if t['state'] == 'FAILED'), None)
    if failed:raise RemoteFailure(failed['error'] or 'REMOTE_PAGE_FAILED')
    for task in tasks:
        if task['state'] == 'RESULT_READY':collect(api, job, task)
    tasks = rows(api, job['id'])
    completed = [t for t in tasks if t['state'] == 'DONE']
    # Global slots cover all projects, so several uploading users cannot each
    # start another two functions. Expired cancelled tasks release their slots.
    with api.db() as conn:
        conn.execute("UPDATE remote_pages SET state='FAILED',error='REMOTE_TASK_EXPIRED' WHERE state IN ('SUBMITTING','SUBMITTED','AMBIGUOUS') AND deadline>0 AND deadline<?", (time.time(),))
        active = conn.execute("SELECT COUNT(*) FROM remote_pages WHERE state IN ('PREPARED','SUBMITTING','SUBMITTED','AMBIGUOUS')").fetchone()[0]
    for task in tasks:
        if task['state'] == 'PREPARED' or (task['state'] == 'AMBIGUOUS' and not task['activation'] and time.time() - task['submitted'] > 120):
            reset = submit(api, job, task)
            if reset:break
    present = {t['page_index'] for t in tasks}
    while not reset and active < remote_setup.policy(api.DATA)['concurrency']:
        index = next((i for i in range(progress['pages']) if i not in present), None)
        if index is None:break
        task = prepare(api, job, index)
        present.add(index);active += 1
        reset = submit(api, job, task)
    progress.update(page=len(completed), evidence_run=job['id'], isolation='provider-function',
                    processor='digitalocean', remote_pages_done=[t['page_index'] for t in completed],
                    remote_wait='budget' if reset else 'provider', remote_active=max(0, active))
    progress['remote_callbacks']=sum(t['result_sha'] is not None for t in completed)
    progress['remote_inline_recoveries']=len(completed)-progress['remote_callbacks']
    progress['remote_transport']=[{'page_index':t['page_index'],'source_sha256':t['source_sha'],
                                   'transport_sha256':t['page_sha'],'transfer_bytes':json.loads(t['metadata']).get('transfer_bytes'),
                                   'callback_received':t['result_sha'] is not None,'activation_id':t['activation']} for t in completed]
    progress['ocr_pages'] = sum(bool(json.loads(t['metadata']).get('ocr_used')) for t in completed)
    pipeline.advance(api, job, progress, 'compose' if len(completed) == progress['pages'] else 'extract',
                     next_at=0 if len(completed) == progress['pages'] else reset or time.time() + 5)


def retry(api, conn, run):
    """An explicit project retry rotates failed grants, retaining completed pages."""
    for row in conn.execute("SELECT * FROM remote_pages WHERE run_id=? AND state='FAILED'", (run,)):
        task = dict(row)
        # Recreate a missing temporary source lazily during the next step.
        path, result = paths(api, task['id'])
        result.unlink(missing_ok=True)
        if not path.exists():
            conn.execute('DELETE FROM remote_pages WHERE id=?', (task['id'],))
        else:
            task.update(nonce=secrets.token_hex(16))
            grant_hash = hashlib.sha256(token(api, task).encode()).hexdigest()
            conn.execute("UPDATE remote_pages SET state='PREPARED',activation=NULL,attempts=0,submitted=0,deadline=0,error=NULL,nonce=?,grant_hash=?,expires=? WHERE id=?",
                         (task['nonce'], grant_hash, time.time() + 900, task['id']))


def install(api):
    def grant(request, identity, result=False):
        if not re.fullmatch(r'[a-f0-9-]{36}', identity):raise HTTPException(404, 'Page grant not found.')
        activation = request.headers.get('X-Caesar-Activation', '')
        if not re.fullmatch(r'[a-f0-9]{32}', activation):raise HTTPException(401, 'Worker activation required.')
        supplied = request.headers.get('Authorization', '').removeprefix('Bearer ')
        with api.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('''SELECT t.*,r.state AS run_state,r.actor AS actor FROM remote_pages t
                 JOIN pipeline_runs r ON r.id=t.run_id WHERE t.id=? AND t.tenant=r.tenant''', (identity,)).fetchone()
            if not row or not secrets.compare_digest(hashlib.sha256(supplied.encode()).hexdigest(), row['grant_hash']):
                raise HTTPException(401, 'Page grant not valid.')
            task = dict(row)
            actor = conn.execute('SELECT role FROM users WHERE id=? AND tenant=?', (task['actor'], task['tenant'])).fetchone()
            if task['expires'] < time.time() or task['run_state'] in ('CANCELLED', 'SUPERSEDED') or (not result and task['run_state'] in ('FAILED', 'DONE')) or not actor or actor['role'] == 'viewer':
                raise HTTPException(410, 'Page grant expired or revoked.')
            if task['activation'] and task['activation'] != activation:
                raise HTTPException(409, 'Another activation already owns this page.')
            if not result:
                if task['source_reads'] >= 4:raise HTTPException(429, 'Page transfer allowance reached.')
                conn.execute("UPDATE remote_pages SET activation=?,source_reads=source_reads+1,state=CASE WHEN state IN ('DONE','RESULT_READY') THEN state ELSE 'SUBMITTED' END WHERE id=?", (activation, identity))
            elif task['activation'] != activation:
                raise HTTPException(409, 'Source page must be claimed before result delivery.')
            task['activation'] = activation
            return task

    @api.app.get('/api/v1/worker/pages/{identity}/source')
    def source(identity: str, request: Request):
        task = grant(request, identity)
        path, _ = paths(api, identity)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PAGE or hashlib.sha256(path.read_bytes()).hexdigest() != task['page_sha']:
            raise HTTPException(409, 'Source page integrity check failed.')
        return api.FileResponse(path, media_type='application/pdf', headers={'Cache-Control': 'no-store'})

    @api.app.post('/api/v1/worker/pages/{identity}/result')
    async def result(identity: str, request: Request):
        task = grant(request, identity, result=True)
        if request.headers.get('Content-Type', '').split(';')[0] != 'application/gzip':
            raise HTTPException(415, 'Compressed page evidence required.')
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_RESULT:raise HTTPException(413, 'Page result exceeds transfer limit.')
        digest = hashlib.sha256(body).hexdigest()
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:content = stream.read(MAX_RESULT + 1)
            if len(content) > MAX_RESULT:raise ValueError()
            value = validate_result(task, json.loads(content))
        except Exception:
            raise HTTPException(422, 'Invalid page evidence identity, geometry, schema or limits.') from None
        with api.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = conn.execute('SELECT * FROM remote_pages WHERE id=?', (identity,)).fetchone()
            state = conn.execute('SELECT state FROM pipeline_runs WHERE id=?', (task['run_id'],)).fetchone()
            if not state or state['state'] in ('CANCELLED', 'SUPERSEDED'):
                raise HTTPException(410, 'Page run revoked during result delivery.')
            if current['activation'] != task['activation'] or current['grant_hash'] != task['grant_hash'] or current['expires'] < time.time():
                raise HTTPException(410, 'Page grant changed during result delivery.')
            if current['result_sha']:
                if current['result_sha'] != digest:raise HTTPException(409, 'A different result is already stored.')
                return {'accepted': True, 'duplicate': True}
            used=conn.execute('SELECT COALESCE(SUM(result_bytes),0) FROM remote_pages WHERE run_id=?',(task['run_id'],)).fetchone()[0]
            if used+len(content)>MAX_RUN_EVIDENCE:
                raise HTTPException(413,'Drawing extraction evidence allowance reached.')
            write(paths(api, identity)[1], value)
            conn.execute("UPDATE remote_pages SET state='RESULT_READY',result_sha=?,result_bytes=?,error=NULL WHERE id=?", (digest,len(content), identity))
            conn.execute("UPDATE pipeline_runs SET next_at=0 WHERE id=? AND state='QUEUED'", (task['run_id'],))
        diag.emit(api.DATA, 'provider.page.delivered', run_id=task['run_id'], task_id=identity,
                  page=task['page_index'] + 1, transfer_bytes=len(body), evidence_bytes=len(content))
        return {'accepted': True}
