"""Private Functions setup for normal project processing, outside Passenger."""
import base64
import hashlib
import shutil
import time
from pathlib import Path
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from services.api import digitalocean as provider
from services.api import diagnostics as diag
from services.api.updates import read, write

DEFAULT = {'enabled': False, 'region': 'syd1', 'concurrency': 2,
           'daily_limit': 100, 'monthly_limit': 500, 'attempt_limit': 2}
ACTION = '/actions/caesar-demo/extract-page'


def directory(data):
    return provider.directory(data) / 'processing'


def policy(data):
    return {**DEFAULT, **read(directory(data) / 'policy.json')}


def version(api):
    files = [api.ROOT / 'scripts/build_functions_demo.py', api.ROOT / 'packages/automation/extract.py']
    files += sorted((api.ROOT / 'serverless/digitalocean/function').glob('*.py'))
    return hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest()


def status(data):
    value = read(directory(data) / 'state.json')
    return {key: value[key] for key in ('state', 'stage', 'updated', 'error', 'code_sha256', 'package_sha256') if key in value}


def update(data, stage, state='running', **extra):
    value = {**read(directory(data) / 'state.json'), 'stage': stage, 'state': state,
             'updated': time.time(), **extra}
    write(directory(data) / 'state.json', value)
    diag.emit(data, 'provider.processing.setup', stage=stage, state=state, error_code=value.get('error'))
    return value


def ensure(api):
    if not policy(api.DATA)['enabled']:
        return False
    wanted = version(api)
    previous = status(api.DATA)
    if previous.get('code_sha256') != wanted:
        write(directory(api.DATA) / 'state.json', {'state': 'queued', 'stage': 'build',
              'code_sha256': wanted, 'updated': time.time()})
    return True


def advance(api):
    if not ensure(api):
        return False
    state = status(api.DATA)
    if state.get('state') not in ('queued', 'running'):
        return False
    home = directory(api.DATA)
    context = provider.TRACE_DATA.set(api.DATA)
    try:
        credential = provider.credentials(api.DATA).get('token')
        if not credential:
            raise provider.ProviderError('PROVIDER_DISCONNECTED')
        stage = state.get('stage', 'build')
        if stage == 'build':
            update(api.DATA, 'build')
            from scripts.build_functions_demo import build
            work = home / 'build'
            if work.exists():shutil.rmtree(work)
            build(work)
            manifest = read(work / 'build-report.json')
            update(api.DATA, 'namespace', package_sha256=manifest['zip_sha256'])
        elif stage == 'namespace':
            label = 'caesar-demo-' + hashlib.sha256(str(api.DATA.resolve()).encode()).hexdigest()[:10]
            region = policy(api.DATA)['region']
            available = provider.namespaces(provider.request(provider.API, 'Bearer ' + credential))
            matches = [n for n in available if n.get('label') == label and n.get('region') == region]
            if len(matches) > 1:raise provider.ProviderError('NAMESPACE_AMBIGUOUS')
            namespace = provider.namespace_details(credential, matches[0]) if matches else provider.request(
                provider.API, 'Bearer ' + credential, 'POST', {'label': label, 'region': region})['namespace']
            write(home / 'namespace.json', namespace)
            update(api.DATA, 'deploy')
        elif stage == 'deploy':
            namespace = read(home / 'namespace.json')
            content = (home / 'build/extract.zip').read_bytes()
            if hashlib.sha256(content).hexdigest() != state['package_sha256']:
                raise provider.ProviderError('BUILD_IDENTITY_MISMATCH')
            provider.namespace_api(namespace, '/packages/caesar-demo?overwrite=true', 'PUT', {'publish': False})
            provider.namespace_api(namespace, ACTION + '?overwrite=true', 'PUT', {
                'exec': {'kind': 'python:3.12', 'code': base64.b64encode(content).decode(), 'binary': True, 'main': 'main'},
                'limits': {'timeout': 240000, 'memory': 1024, 'logs': 64},
                'annotations': [{'key': 'web-export', 'value': False}], 'publish': False})
            shutil.rmtree(home / 'build', ignore_errors=True)
            update(api.DATA, 'complete', 'ready', error=None)
        else:raise provider.ProviderError('PROCESSING_SETUP_STAGE_INVALID')
    except Exception as error:
        diag.exception(api.DATA, 'provider.processing.setup_failed', error)
        update(api.DATA, state.get('stage', 'build'), 'failed', error=str(error) if isinstance(error, provider.ProviderError) else 'PROCESSING_SETUP_FAILED')
    finally:
        provider.TRACE_DATA.reset(context)
    return True


def call(api, path, method='GET', body=None, pending=False):
    if not ensure(api) or status(api.DATA).get('state') != 'ready':
        from services.api.pipeline_executor import WorkerUnavailable
        raise WorkerUnavailable('REMOTE_WORKER_PREPARING')
    namespace = read(directory(api.DATA) / 'namespace.json')
    context = provider.TRACE_DATA.set(api.DATA)
    try:
        return provider.namespace_api(namespace, path, method, body, pending)
    finally:
        provider.TRACE_DATA.reset(context)


def install(api):
    def operator(actor=Depends(api.user)):
        if actor['role'] != 'admin' or (not api.LOCAL_DEMO and actor['id'] != 'admin'):
            raise HTTPException(403, 'Hosting administrator access required.')
        return actor

    class Policy(BaseModel):
        model_config = ConfigDict(extra='forbid')
        enabled: bool
        concurrency: int = Field(default=2, ge=1, le=2)
        daily_limit: int = Field(default=100, ge=1, le=500)
        monthly_limit: int = Field(default=500, ge=1, le=5000)

    @api.app.get('/api/v1/system/digitalocean/processing')
    def get(actor=Depends(operator)):
        return {'policy': policy(api.DATA), 'worker': status(api.DATA),
                'maximum_compute_usd_per_month_before_allowance': policy(api.DATA)['monthly_limit'] * 240 * .0000185}

    @api.app.post('/api/v1/system/digitalocean/processing')
    def configure(body: Policy, actor=Depends(operator)):
        if body.enabled and not provider.credentials(api.DATA).get('token'):
            raise HTTPException(409, 'Connect DigitalOcean first.')
        write(directory(api.DATA) / 'policy.json', {**policy(api.DATA), **body.model_dump()})
        if body.enabled:
            if status(api.DATA).get('state') == 'failed':
                write(directory(api.DATA) / 'state.json', {'state': 'queued', 'stage': 'build', 'code_sha256': version(api), 'updated': time.time()})
            ensure(api)
        diag.emit(api.DATA, 'provider.processing.policy_changed', **body.model_dump(), actor_id=actor['id'])
        return get(actor)
