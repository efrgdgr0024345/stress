"""Private native PDF previews and explicit graphical-only layout acceptance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from fastapi import Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal


class PreviewInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    confirmed:Literal[True]


class AcceptInput(PreviewInput):
    proposal_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    reason:str=Field(min_length=10,max_length=3000)


def _source_path(api,source_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',source_id):raise ValueError('Invalid registered source identity.')
    return api.DATA/'sources'/f'{source_id}.pdf'


def _verify_sources(api,project):
    for source_id,expected in {s['source_id']:s['sha256'] for s in project['sheets']}.items():
        path=_source_path(api,source_id)
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise HTTPException(409,'Registered source bytes changed or are unavailable. Restore the original source before reviewing native layout.')


def _folder(api,project,version,proposal):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',project['id']) or not re.fullmatch(r'[a-f0-9]{64}',proposal):
        raise HTTPException(422,'Invalid native layout preview identity.')
    base=api.DATA/'pdf-layout-previews'/project['id']
    folder=base/f'r{version}-{proposal}'
    if base.parent.is_symlink() or base.is_symlink() or folder.is_symlink():raise HTTPException(409,'Private preview storage requires operator attention.')
    return folder


def _accepted(project):
    from packages.pdf import accepted_plan_current
    review=project.get('native_layout_review')
    if not review:return None
    current=accepted_plan_current(project)
    return {**deepcopy(review),'current':current,'stale':not current,
            'proposal_sha256':review.get('proposal_sha256') or review.get('input_sha256')}


def install(api):
    path='/api/v1/projects/{project_id}/pdf-layout'

    def read(project_id,actor):
        with api.db() as conn:p=api.project_read(project_id,actor,conn)
        p['issues']=api.validate(p)
        _verify_sources(api,p)
        return p

    @api.app.get(path)
    def report(project_id:str,actor=Depends(api.user)):
        p=read(project_id,actor)
        return {'schema':'native-layout-1','revision':p['version'],'can_edit':actor['role'] in ('admin','engineer'),
                'accepted':_accepted(p),'source_pages':len(p['sheets']),
                'point_instances':sum(len(n['instances']) for n in p['nodes']),
                'engineering_values_modified':False}

    @api.app.post(path+'/preview')
    def preview(project_id:str,body:PreviewInput,actor=Depends(api.editor)):
        p=read(project_id,actor)
        if p['version']!=body.version:raise HTTPException(409,'Project changed. Reload before generating the native layout preview.')
        if not p['sheets']:raise HTTPException(422,'Upload a source drawing before reviewing native layout.')
        from packages.pdf import plan_layout,export_bundle
        try:plan=plan_layout(p,lambda sid:_source_path(api,sid))
        except ValueError as error:raise HTTPException(422,str(error)) from None
        proposal=plan['input_sha256']
        result={**plan,'proposal_sha256':proposal,'accepted':_accepted(p)}
        if not plan['can_export']:return result
        folder=_folder(api,p,p['version'],proposal)
        folder.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with tempfile.TemporaryDirectory(prefix='.building-',dir=folder.parent) as temporary:
            staged=Path(temporary);bundle=staged/'preview.zip'
            try:export_bundle(deepcopy(p),lambda sid:_source_path(api,sid),bundle)
            except ValueError as error:raise HTTPException(422,str(error)) from None
            with zipfile.ZipFile(bundle) as archive:
                pdf=archive.read('annotated-review.pdf');manifest=json.loads(archive.read('annotation-manifest.json'))
            with api.db() as conn:current=api.project_read(project_id,actor,conn)
            if current['version']!=p['version']:raise HTTPException(409,'Project changed while the native PDF was being built. Preview the current revision.')
            metadata={'revision':p['version'],'proposal_sha256':proposal,'project_id':p['id'],
                'pdf_sha256':hashlib.sha256(pdf).hexdigest(),'manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
                'annotations':manifest,'report':result}
            (staged/'native.pdf').write_bytes(pdf)
            (staged/'metadata.json').write_text(json.dumps(metadata))
            folder.mkdir(exist_ok=True,mode=0o700)
            for name in ('native.pdf','metadata.json'):
                target=folder/name
                if target.is_symlink():raise HTTPException(409,'Private preview storage requires operator attention.')
                (staged/name).replace(target);target.chmod(0o600)
        # Retain a few immutable revision previews without unbounded disk growth.
        previous=sorted((v for v in folder.parent.iterdir() if v.is_dir() and not v.is_symlink() and v.name.startswith('r')),
                        key=lambda v:v.stat().st_mtime,reverse=True)
        for old in previous[8:]:shutil.rmtree(old)
        api.diag.emit(api.DATA,'pdf.layout.preview.completed',revision=p['version'],objects=len(manifest),pages=len(p['sheets']))
        return result

    @api.app.post(path+'/accept')
    def accept(project_id:str,body:AcceptInput,actor=Depends(api.editor)):
        def update(p):
            from packages.pdf import plan_layout,apply_layout
            _verify_sources(api,p)
            p['issues']=api.validate(p)
            try:
                plan=plan_layout(p,lambda sid:_source_path(api,sid))
                if plan['input_sha256']!=body.proposal_sha256:raise ValueError('Native layout source or proposal changed. Preview the current drawing before accepting placement.')
                if not plan['can_export']:raise ValueError('Resolve the typed native layout exceptions before accepting placement.')
                apply_layout(p,plan,actor['id'],api.now(),body.reason)
            except ValueError as error:raise HTTPException(422,str(error)) from None
            p['layout_reviewed']=False
        return api.change(project_id,body.version,actor,'Accepted graphical native PDF placement only; no physical coordinates, stations or engineering approval changed',update)

    def cached(project_id,version,proposal,actor):
        p=read(project_id,actor)
        if p['version']!=version:raise HTTPException(409,'Project changed. Generate a native PDF preview for the current revision.')
        folder=_folder(api,p,version,proposal)
        from packages.pdf import layout_input_sha256
        if layout_input_sha256(p)!=proposal:raise HTTPException(409,'Native layout inputs changed. Generate a fresh preview before downloading.')
        try:
            if any((folder/name).is_symlink() for name in ('metadata.json','native.pdf')):raise ValueError()
            metadata=json.loads((folder/'metadata.json').read_text());pdf=(folder/'native.pdf').read_bytes()
            manifest_sha=hashlib.sha256(json.dumps(metadata['annotations'],sort_keys=True).encode()).hexdigest()
            if metadata['revision']!=version or metadata['project_id']!=project_id or metadata['proposal_sha256']!=proposal or hashlib.sha256(pdf).hexdigest()!=metadata['pdf_sha256'] or manifest_sha!=metadata['manifest_sha256']:
                raise ValueError()
        except (OSError,ValueError,KeyError):raise HTTPException(409,'Native PDF preview is unavailable. Generate it again from this revision.') from None
        return metadata,pdf

    @api.app.get(path+'/native.pdf')
    def native(project_id:str,version:int=Query(ge=1),proposal_sha256:str=Query(pattern=r'^[a-f0-9]{64}$'),actor=Depends(api.user)):
        metadata,pdf=cached(project_id,version,proposal_sha256,actor)
        return api.Response(pdf,media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="caesar-native-layout-r{version}.pdf"'})

    @api.app.get(path+'/manifest')
    def manifest(project_id:str,version:int=Query(ge=1),proposal_sha256:str=Query(pattern=r'^[a-f0-9]{64}$'),actor=Depends(api.user)):
        metadata,_=cached(project_id,version,proposal_sha256,actor)
        return {'schema':'native-layout-manifest-1','revision':version,'proposal_sha256':proposal_sha256,
                'annotations':metadata['annotations'],'summary':metadata['report']['summary'],
                'source_content_hashes':metadata['report'].get('source_content_hashes'),
                'pdf_sha256':metadata['pdf_sha256']}
