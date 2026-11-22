"""Operator-only provider connection and bounded, separately executed demo.

Account credentials never enter function inputs, public status or diagnostics.
The existing account cron runner advances durable stages outside Passenger.
"""
import base64
from contextvars import ContextVar
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from uuid import uuid4

from fastapi import Depends, HTTPException, Request as WebRequest
from pydantic import BaseModel, ConfigDict, Field

from services.api import diagnostics as diag
from services.api.updates import read, write, lock

REGIONS = ('syd1', 'sgp1', 'nyc3', 'fra1')
API = 'https://api.digitalocean.com/v2/functions/namespaces'
ACTIVE = ('queued', 'running', 'waiting')
MAX_PDF = 700000
TRACE_DATA = ContextVar('provider_trace_data', default=None)


class ProviderError(Exception):
    pass


def response_shape(value):
    """Only field names/types from a fixed allowlist, never provider values."""
    if not isinstance(value, dict):
        return {'root': type(value).__name__}
    return {key: type(value[key]).__name__ for key in
            ('namespaces', 'namespace', 'response', 'result', 'activationId', 'error') if key in value}


def namespaces(response):
    # DigitalOcean serializes an empty Go slice as null, not necessarily [].
    if 'namespaces' not in response or (response['namespaces'] is not None and not isinstance(response['namespaces'], list)):
        raise ProviderError('PROVIDER_RESPONSE_INVALID')
    values = response['namespaces'] or []
    if any(not isinstance(value, dict) for value in values):
        raise ProviderError('PROVIDER_RESPONSE_INVALID')
    return values


def namespace_details(token, summary):
    name = summary.get('namespace', '')
    if not re.fullmatch(r'fn-[a-f0-9-]{36}', name):
        raise ProviderError('NAMESPACE_ID_REJECTED')
    response = request(API + '/' + quote(name, safe=''), 'Bearer ' + token)
    value = response.get('namespace')
    if not isinstance(value, dict) or value.get('namespace') != name:
        raise ProviderError('NAMESPACE_IDENTITY_MISMATCH')
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(url, authorization, method='GET', body=None, pending=False, acknowledge=False):
    """Only callers construct URLs; never follow redirects with credentials."""
    req = Request(url, data=json.dumps(body).encode() if body is not None else None,
                  method=method, headers={'Authorization': authorization,
                  'Content-Type': 'application/json', 'User-Agent': 'CAESAR-provider-demo'})
    started = time.monotonic()
    target = ('activation' if '/activations/' in url else 'action' if '/actions/' in url else
              'package' if '/packages/' in url else 'namespaces')
    metadata = {'method': method, 'target': target}
    def trace(event, level='DEBUG', **extra):
        if TRACE_DATA.get() is not None:
            diag.emit(TRACE_DATA.get(), event, level, **metadata,
                      duration_ms=round((time.monotonic() - started) * 1000), **extra)
    try:
        with build_opener(NoRedirect()).open(req, timeout=60) as response:
            metadata['http_status'] = response.status
            identity = response.headers.get('X-Request-Id', '')
            if re.fullmatch(r'[a-zA-Z0-9-]{1,128}', identity):
                metadata['provider_request_id'] = identity
            media = response.headers.get('Content-Type', '').split(';')[0]
            metadata['media_type'] = media if media in ('application/json', 'text/html', 'text/plain') else 'other'
            if acknowledge:
                # OpenWhisk echoes the complete 40+ MB base64 action code in a
                # successful PUT. The HTTP acknowledgement is sufficient; do
                # not buffer or log the uploaded binary again.
                trace('provider.http.completed', acknowledgement_only=True)
                return {'accepted': True}
            content = response.read(2_000_001)
        metadata['response_bytes'] = len(content)
        if len(content) > 2_000_000:
            trace('provider.http.rejected', 'ERROR', error_code='PROVIDER_RESPONSE_TOO_LARGE')
            raise ProviderError('PROVIDER_RESPONSE_TOO_LARGE')
        try:
            value = json.loads(content)
        except ValueError:
            trace('provider.http.rejected', 'ERROR', error_code='PROVIDER_JSON_INVALID')
            raise ProviderError('PROVIDER_JSON_INVALID') from None
        trace('provider.http.completed', shape=response_shape(value))
        if not isinstance(value, dict):
            raise ProviderError('PROVIDER_RESPONSE_INVALID')
        return value
    except HTTPError as error:
        metadata['http_status'] = error.code
        identity = error.headers.get('X-Request-Id', '') if error.headers else ''
        if re.fullmatch(r'[a-zA-Z0-9-]{1,128}', identity):
            metadata['provider_request_id'] = identity
        if pending and error.code == 404:
            trace('provider.http.pending')
            return None
        trace('provider.http.failed', 'ERROR', error_code=f'PROVIDER_HTTP_{error.code}')
        raise ProviderError(f'PROVIDER_HTTP_{error.code}') from None
    except (URLError, TimeoutError, OSError):
        trace('provider.http.failed', 'ERROR', error_code='PROVIDER_CONNECTION_FAILED')
        raise ProviderError('PROVIDER_CONNECTION_FAILED') from None


def directory(data):
    path = Path(data) / 'providers' / 'digitalocean'
    for part in (path.parent, path):
        if part.is_symlink():
            raise ProviderError('PRIVATE_STORAGE_UNSAFE')
        part.mkdir(mode=0o700, exist_ok=True)
        part.chmod(0o700)
    return path


def credentials(data):
    path = directory(data) / 'credentials.json'
    if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_mode & 0o077)):
        raise ProviderError('PRIVATE_STORAGE_UNSAFE')
    return read(path)


def connection(data):
    value = credentials(data)
    return {'configured': bool(value.get('token')), 'verified_at': value.get('verified_at'),
            'storage': 'private-server-file', 'regions': list(REGIONS)}


def save(data, token):
    if not isinstance(token, str) or not 20 <= len(token) <= 512 or not re.fullmatch(r'[A-Za-z0-9_-]+', token):
        raise ProviderError('TOKEN_FORMAT_INVALID')
    # Test the required Functions permission before replacing a working token.
    context = TRACE_DATA.set(data)
    try:
        response = request(API, 'Bearer ' + token)
        available = namespaces(response)
        diag.emit(data, 'provider.namespaces.checked', namespaces_count=len(available),
                  empty_list_was_null=response['namespaces'] is None)
    finally:
        TRACE_DATA.reset(context)
    credentials(data)  # Validate the destination before replacing it.
    write(directory(data) / 'credentials.json', {'token': token, 'verified_at': time.time()})
    return connection(data)


def current(data):
    return read(directory(data) / 'demo.json')


def public_job(data):
    value = current(data)
    allowed = ('id', 'state', 'stage', 'created', 'updated', 'project_id', 'project_title',
               'region', 'source_sha256', 'page_count', 'page', 'error', 'events', 'report', 'preview')
    return {key: value[key] for key in allowed if key in value}


def record(data, job, stage, state='running', **changes):
    job.update(stage=stage, state=state, updated=time.time(), **changes)
    entry = {'stage': stage, 'state': state, 'at': job['updated']}
    if job.get('error'):
        entry['error'] = job['error']
    job.setdefault('events', []).append(entry)
    job['events'] = job['events'][-80:]
    write(directory(data) / 'demo.json', job)
    diag.emit(data, 'provider.demo.progress', job_id=job['id'], stage=stage,
              state=state, error_code=job.get('error'))


def queue(api, actor, project_id, source_id, region):
    home = directory(api.DATA)
    with lock(home):
        if current(api.DATA).get('state') in ACTIVE:
            raise HTTPException(409, 'A worker test is already active. Follow its progress below.')
        if not credentials(api.DATA).get('token'):
            raise HTTPException(409, 'Connect DigitalOcean first.')
        with api.db() as conn:
            project = api.project_read(project_id, actor, conn)
        sheets = sorted((s for s in project['sheets'] if s['source_id'] == source_id), key=lambda s: s['page_index'])[:2]
        if not sheets or not re.fullmatch(r'[a-f0-9-]{36}', source_id):
            raise HTTPException(404, 'Select an active PDF drawing.')
        source = api.DATA / 'sources' / f'{source_id}.pdf'
        if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_PDF:
            raise HTTPException(422, 'This demo supports PDFs up to 700 KB and tests their first two registered pages.')
        content = source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if not content.startswith(b'%PDF-') or any(s['sha256'] != digest for s in sheets):
            raise HTTPException(409, 'Drawing identity changed. Reload the project.')
        # This is a one-result demonstration, not a growing document archive.
        # The original project PDF remains in the normal project source store.
        previous = current(api.DATA).get('id', '')
        if re.fullmatch(r'[a-f0-9-]{36}', previous):
            shutil.rmtree(home / previous, ignore_errors=True)
        job_id = str(uuid4())
        work = home / job_id
        work.mkdir(mode=0o700)
        (work / 'source.pdf').write_bytes(content)
        (work / 'source.pdf').chmod(0o600)
        write(work / 'project.json', project)
        job = {'id': job_id, 'created': time.time(), 'project_id': project_id,
               'project_title': project['title'], 'region': region, 'source_sha256': digest,
               'page_count': len(sheets), 'page': 0, 'sheets': sheets, 'results': []}
        record(api.DATA, job, 'build', 'queued')
        return public_job(api.DATA)


def namespace_api(namespace, path, method='GET', body=None, pending=False):
    host = namespace.get('api_host', '')
    parts = urlsplit(host)
    # Credential-bearing requests can only reach the documented provider API.
    if (parts.scheme != 'https' or not parts.hostname or
        not parts.hostname.endswith('.doserverless.co') or parts.username or parts.password or
        parts.port not in (None, 443) or parts.path not in ('', '/') or parts.query or parts.fragment):
        raise ProviderError('NAMESPACE_HOST_REJECTED')
    name = namespace.get('namespace', '')
    if not re.fullmatch(r'fn-[a-f0-9-]{36}', name) or not re.fullmatch(r'[a-f0-9-]{36}', namespace.get('uuid', '')):
        raise ProviderError('NAMESPACE_ID_REJECTED')
    if not isinstance(namespace.get('key'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,512}', namespace['key']):
        raise ProviderError('NAMESPACE_CREDENTIALS_MISSING')
    auth = base64.b64encode((namespace['uuid'] + ':' + namespace['key']).encode()).decode()
    return request(host.rstrip('/') + '/api/v1/namespaces/' + quote(name, safe='') + path,
                   'Basic ' + auth, method, body, pending,
                   acknowledge=method == 'PUT' and path.startswith('/actions/'))


def find_result(value):
    if isinstance(value, dict):
        if value.get('format') == 'caesar-function-result-1':
            return value
        for key in ('body', 'result', 'response'):
            if key in value:
                result = find_result(value[key])
                if result:
                    return result
    return None


def advance(api):
    """Run one durable stage under the existing separate runner's global lock."""
    job = current(api.DATA)
    if job.get('state') not in ACTIVE or job.get('next_at', 0) > time.time():
        return False
    work = directory(api.DATA) / job['id']
    stage = job['stage']
    context = TRACE_DATA.set(api.DATA)
    try:
        token = credentials(api.DATA).get('token')
        if not token:
            raise ProviderError('PROVIDER_DISCONNECTED')
        if stage == 'build':
            record(api.DATA, job, 'build')
            from scripts.build_functions_demo import build
            output = work / 'build'
            if output.exists():
                shutil.rmtree(output)
            build(output)
            manifest = read(output / 'build-report.json')
            job['build_sha256'] = manifest['zip_sha256']
            record(api.DATA, job, 'namespace')
        elif stage == 'namespace':
            label = 'caesar-demo-' + hashlib.sha256(str(api.DATA.resolve()).encode()).hexdigest()[:10]
            response = request(API, 'Bearer ' + token)
            matches = [n for n in namespaces(response) if n.get('label') == label and n.get('region') == job['region']]
            if len(matches) > 1:
                raise ProviderError('NAMESPACE_AMBIGUOUS')
            namespace = namespace_details(token, matches[0]) if matches else request(API, 'Bearer ' + token, 'POST', {'label': label, 'region': job['region']})['namespace']
            write(work / 'namespace.json', namespace)
            record(api.DATA, job, 'deploy')
        elif stage == 'deploy':
            namespace = read(work / 'namespace.json')
            package = (work / 'build/extract.zip').read_bytes()
            if hashlib.sha256(package).hexdigest() != job['build_sha256']:
                raise ProviderError('BUILD_IDENTITY_MISMATCH')
            namespace_api(namespace, '/packages/caesar-demo?overwrite=true', 'PUT', {'publish': False})
            namespace_api(namespace, '/actions/caesar-demo/extract?overwrite=true', 'PUT', {
                'exec': {'kind': 'python:3.12', 'code': base64.b64encode(package).decode(), 'binary': True, 'main': 'main'},
                'limits': {'timeout': 240000, 'memory': 1024, 'logs': 64},
                'annotations': [{'key': 'web-export', 'value': False}], 'publish': False})
            record(api.DATA, job, 'invoke')
        elif stage == 'invoke':
            source = (work / 'source.pdf').read_bytes()
            if hashlib.sha256(source).hexdigest() != job['source_sha256']:
                raise ProviderError('SOURCE_IDENTITY_MISMATCH')
            # Checkpoint before submission: an ambiguous network interruption
            # fails visibly rather than silently billing a duplicate invocation.
            record(api.DATA, job, 'submitting')
            response = namespace_api(read(work / 'namespace.json'), '/actions/caesar-demo/extract?blocking=false', 'POST', {
                'pdf_base64': base64.b64encode(source).decode(), 'sha256': job['source_sha256'],
                'page': job['sheets'][job['page']]['page_index']})
            activation = response.get('activationId', '')
            if not re.fullmatch(r'[a-f0-9]{32}', activation):
                raise ProviderError('ACTIVATION_ID_INVALID')
            record(api.DATA, job, 'poll', 'waiting', activation=activation, deadline=time.time() + 360, next_at=time.time() + 10)
        elif stage == 'submitting':
            raise ProviderError('SUBMISSION_INTERRUPTED_CHECK_PROVIDER')
        elif stage == 'poll':
            if time.time() > job['deadline']:
                raise ProviderError('FUNCTION_DEADLINE_EXCEEDED')
            response = namespace_api(read(work / 'namespace.json'), '/activations/' + job['activation'], pending=True)
            if response is None or 'response' not in response:
                job['next_at'] = time.time() + 10
                write(directory(api.DATA) / 'demo.json', job)
                return False
            result = find_result(response)
            completion = response.get('response', {})
            provider_status = completion.get('status')
            own_error = result.get('error') if isinstance(result, dict) else None
            diag.emit(api.DATA, 'provider.function.completed', job_id=job['id'],
                      page=job['page'] + 1, activation_id=job['activation'],
                      duration_ms=response.get('duration') if type(response.get('duration')) is int else None,
                      success=completion.get('success') is True,
                      provider_status=provider_status if provider_status in ('success', 'application error', 'developer error', 'whisk internal error') else 'other',
                      worker_error=own_error if isinstance(own_error, str) and re.fullmatch(r'[A-Z0-9_]{1,80}', own_error) else None)
            if not result or result.get('ok') is not True or result.get('encoding') != 'gzip+base64':
                raise ProviderError('FUNCTION_PROCESSING_FAILED')
            packed = base64.b64decode(result['evidence'], validate=True)
            with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
                content = stream.read(16 * 1024**2 + 1)
            if len(content) > 16 * 1024**2:
                raise ProviderError('EVIDENCE_LIMIT')
            evidence = json.loads(content)
            from packages.automation.contracts import PageEvidence
            evidence = PageEvidence.model_validate({**evidence, 'isolation': 'provider-function'}).model_dump()
            sheet = job['sheets'][job['page']]
            if evidence['source_sha256'] != job['source_sha256'] or evidence['page_index'] != sheet['page_index']:
                raise ProviderError('EVIDENCE_IDENTITY_MISMATCH')
            write(work / f"page-{job['page']}.json", evidence)
            from packages.automation.recognize import materials
            proposed, _, _ = materials(evidence, sheet, job['source_sha256'])
            job['results'].append({'page': sheet['page_index'] + 1, 'words': len(evidence['words']),
                                   'ocr_used': evidence['ocr_used'], 'material_proposals': len(proposed),
                                   'elapsed_ms': result.get('elapsed_ms'), 'parser_peak_rss_kib': result.get('parser_peak_rss_kib')})
            diag.emit(api.DATA, 'provider.page.completed', job_id=job['id'], **job['results'][-1])
            job['page'] += 1
            job.pop('next_at', None)
            record(api.DATA, job, 'invoke' if job['page'] < job['page_count'] else 'report')
        elif stage == 'report':
            project = read(work / 'project.json')
            proposed = []
            from packages.automation.recognize import materials
            for index, sheet in enumerate(job['sheets']):
                rows, _, _ = materials(read(work / f'page-{index}.json'), sheet, job['source_sha256'])
                proposed.extend(rows)
            project = deepcopy(project)
            project['materials'] = proposed
            project['nodes'] = []
            project['layout_reviewed'] = False
            from packages.workbooks import workbook
            from packages.workbooks.csv_export import csv_bundle
            (work / 'results.xlsx').write_bytes(workbook(project))
            (work / 'results.zip').write_bytes(csv_bundle(project))
            report = {'digitalocean_live_tested': True, 'engineering_verified': False,
                      'region': job['region'], 'source_sha256': job['source_sha256'],
                      'pages': job['results'], 'material_proposals': len(proposed),
                      'project_modified': False, 'limits': {'memory_mb': 1024, 'timeout_seconds': 240}}
            write(work / 'report.json', report)
            shutil.rmtree(work / 'build', ignore_errors=True)
            (work / 'namespace.json').unlink(missing_ok=True)
            record(api.DATA, job, 'complete', 'done', report=report,
                   preview=[{k: row.get(k) for k in ('item_no', 'description', 'size', 'quantity', 'family')} for row in proposed[:100]])
        else:
            raise ProviderError('DEMO_STAGE_INVALID')
    except Exception as error:
        diag.exception(api.DATA, 'provider.demo.failed', error, job_id=job['id'], stage=stage)
        code = str(error) if isinstance(error, ProviderError) and re.fullmatch(r'[A-Z0-9_]{1,80}', str(error)) else 'DEMO_STAGE_FAILED'
        record(api.DATA, job, stage, 'failed', error=code)
    finally:
        TRACE_DATA.reset(context)
    return True


def install(api):
    def operator(actor=Depends(api.user)):
        if actor['role'] != 'admin' or (not api.LOCAL_DEMO and actor['id'] != 'admin'):
            raise HTTPException(403, 'Hosting administrator access required.')
        return actor

    @api.app.get('/api/v1/system/digitalocean')
    def status(actor=Depends(operator)):
        try:
            heartbeat = read(api.DATA / 'pipeline/heartbeat.json').get('at', 0)
            return {**connection(api.DATA), 'demo': public_job(api.DATA), 'runner_ready': heartbeat > time.time() - 300}
        except ProviderError as error:
            raise HTTPException(409, str(error)) from None

    @api.app.post('/api/v1/system/digitalocean')
    async def connect(web_request: WebRequest, actor=Depends(operator)):
        # Read a bounded body ourselves: validation errors must never echo a PAT.
        body = bytearray()
        async for chunk in web_request.stream():
            body.extend(chunk)
            if len(body) > 2048:
                raise HTTPException(413, 'Connection request is too large.')
        try:
            value = json.loads(body)
            if not isinstance(value, dict) or set(value) != {'token'}:
                raise ProviderError('TOKEN_FORMAT_INVALID')
            import asyncio
            result = await asyncio.to_thread(save, api.DATA, value['token'])
        except (ValueError, ProviderError) as error:
            code = str(error) if isinstance(error, ProviderError) else 'TOKEN_FORMAT_INVALID'
            diag.emit(api.DATA, 'provider.connection.failed', 'WARNING', error_code=code)
            raise HTTPException(422, code) from None
        diag.emit(api.DATA, 'provider.connection.saved', actor_id=actor['id'])
        return result

    @api.app.delete('/api/v1/system/digitalocean')
    def disconnect(actor=Depends(operator)):
        home = directory(api.DATA)
        with lock(home):
            if current(api.DATA).get('state') in ACTIVE:
                raise HTTPException(409, 'Wait for the active worker test to finish before disconnecting.')
            credentials(api.DATA)
            (home / 'credentials.json').unlink(missing_ok=True)
        diag.emit(api.DATA, 'provider.connection.removed', actor_id=actor['id'])
        return connection(api.DATA)

    class DemoInput(BaseModel):
        model_config = ConfigDict(extra='forbid')
        project_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
        source_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
        region: str = Field(pattern=r'^(syd1|sgp1|nyc3|fra1)$')

    @api.app.post('/api/v1/system/digitalocean/demo', status_code=202)
    def test(body: DemoInput, actor=Depends(operator)):
        return queue(api, actor, body.project_id, body.source_id, body.region)

    @api.app.get('/api/v1/system/digitalocean/demo/{job_id}/{format}')
    def download(job_id: str, format: str, actor=Depends(operator)):
        job = current(api.DATA)
        if job.get('id') != job_id or job.get('state') != 'done' or format not in ('xlsx', 'csv', 'json'):
            raise HTTPException(404, 'Completed worker result not found.')
        with api.db() as conn:
            api.project_read(job['project_id'], actor, conn)
        filename, media = {'xlsx': ('results.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                           'csv': ('results.zip', 'application/zip'), 'json': ('report.json', 'application/json')}[format]
        return api.FileResponse(directory(api.DATA) / job_id / filename, media_type=media, filename='caesar-worker-demo.' + ('zip' if format == 'csv' else format))
