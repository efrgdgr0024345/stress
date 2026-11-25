"""Tenant-scoped project catalog decisions and independent manufacturer review."""
import hashlib
import json
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field

from packages.catalogs.project_review import (catalog_review_report,prepare_catalog_review,
    record_catalog_decision,record_manufacturer_decision,refresh_project_catalog_reviews)


def load_catalog_versions(api,tenant,conn=None):
    """Read registered immutable datasets; broken source bytes stay unusable."""
    if conn is None:
        with api.db() as connection:return load_catalog_versions(api,tenant,connection)
    sources={r['id']:dict(r) for r in conn.execute('SELECT id,sha256 FROM catalogs WHERE tenant=?',(tenant,))}
    result=[];integrity={}
    for row in conn.execute('SELECT * FROM catalog_versions WHERE tenant=? ORDER BY id',(tenant,)):
        version={**dict(row),'data':json.loads(row['data'])};source=sources.get(version['catalog_id'])
        if version['catalog_id'] not in integrity:
            path=api.DATA/'catalogs'/f"{version['catalog_id']}.xlsx"
            integrity[version['catalog_id']]=bool(source and path.is_file() and not path.is_symlink() and
                hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256'])
        version['source_integrity_current']=bool(integrity[version['catalog_id']] and source and
            version['data'].get('source_sha256')==source['sha256'])
        result.append(version)
    return result


class Prepare(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    confirmed:Literal[True]


class Decision(Prepare):
    material_id:str=Field(min_length=1,max_length=100)
    decision:Literal['ACCEPT_EXACT_MATCH','DECLARE_NA','REOPEN']
    reason_code:Literal['SPECIFICATION_UNCONFIRMED','NO_EXACT_CATALOG_MATCH','CATALOG_FACING_UNSPECIFIED',
        'CATALOG_COMPONENT_TYPE_UNSUPPORTED','API_BORE_UNCONFIRMED','VALVE_MANUFACTURER_DATA_UNAVAILABLE',
        'CATALOG_DATASET_UNAPPROVED','COMPONENT_CLASSIFICATION_UNCONFIRMED','CATALOG_RECORD_INCOMPLETE',
        'SOURCE_SPECIFICATION_AND_DATASET_REVIEWED','REVIEW_REOPENED']
    evidence:str=Field(min_length=10,max_length=3000)
    source_context_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    catalog_version_id:str|None=Field(default=None,max_length=100)
    record_id:str|None=Field(default=None,max_length=100)


class Manufacturer(Prepare):
    material_id:str=Field(min_length=1,max_length=100)
    decision:Literal['CONFIRM','REOPEN']
    vendor:str|None=Field(default=None,max_length=150)
    model:str|None=Field(default=None,max_length=150)
    evidence:str=Field(min_length=20,max_length=3000)
    source_context_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


def install(api):
    path='/api/v1/projects/{project_id}/catalog-review'

    @api.app.get(path)
    def get(project_id:str,actor=Depends(api.user)):
        with api.db() as conn:
            p=api.project_read(project_id,actor,conn);versions=load_catalog_versions(api,actor['tenant'],conn)
        return {**catalog_review_report(p,versions),'revision':p['version'],'can_edit':actor['role'] in ('admin','engineer')}

    @api.app.post(path+'/prepare')
    def prepare(project_id:str,body:Prepare,actor=Depends(api.editor)):
        def update(p):
            versions=load_catalog_versions(api,actor['tenant'])
            prepare_catalog_review(p,versions,actor['id'],api.now())
            refresh_project_catalog_reviews(p,versions)
        return api.change(project_id,body.version,actor,'Prepared source-bound project catalog proposals; no data or manufacturer approval inferred',update)

    @api.app.post(path+'/decision')
    def decide(project_id:str,body:Decision,actor=Depends(api.editor)):
        def update(p):
            versions=load_catalog_versions(api,actor['tenant'])
            try:record_catalog_decision(p,versions,body.material_id,body.decision,body.reason_code,
                body.evidence,actor['id'],api.now(),body.source_context_sha256,body.catalog_version_id,body.record_id)
            except ValueError as error:raise HTTPException(422,str(error)) from None
            refresh_project_catalog_reviews(p,versions)
        return api.change(project_id,body.version,actor,'Recorded source-bound catalog review: '+body.decision,update)

    @api.app.post(path+'/manufacturer')
    def manufacturer(project_id:str,body:Manufacturer,actor=Depends(api.editor)):
        def update(p):
            try:record_manufacturer_decision(p,body.material_id,body.decision,body.vendor,body.model,
                body.evidence,actor['id'],api.now(),body.source_context_sha256)
            except ValueError as error:raise HTTPException(422,str(error)) from None
            refresh_project_catalog_reviews(p,load_catalog_versions(api,actor['tenant']))
        return api.change(project_id,body.version,actor,'Recorded independent project manufacturer review: '+body.decision,update)
