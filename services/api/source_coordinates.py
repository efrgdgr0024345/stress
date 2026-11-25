"""Explicit acceptance of actual printed XYZ; source location review is separate."""
from copy import deepcopy
from decimal import Decimal
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from packages.engineering import dimension_mm
from packages.physical import prepare
from packages.physical.constraints import MAX_CONSTRAINTS
from packages.physical.source_coordinates import proposals,inspection_fingerprint


class Accept(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    tolerance_text:str=Field(min_length=1,max_length=100)
    evidence:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]


def install(api):
    @api.app.get('/api/v1/projects/{project_id}/physical-model/source-coordinates')
    def get(project_id:str,actor=Depends(api.user)):
        with api.db() as c:p=api.project_read(project_id,actor,c)
        return {'proposals':proposals(p),'can_edit':actor['role'] in ('admin','engineer'),'revision':p['version']}

    @api.app.post('/api/v1/projects/{project_id}/physical-model/source-coordinates/{candidate_id}/accept')
    def accept(project_id:str,candidate_id:str,body:Accept,actor=Depends(api.editor)):
        def update(p):
            records=[r for r in proposals(p) if r['candidate_id']==candidate_id]
            if len(records)!=3 or {r['axis'] for r in records}!={'X','Y','Z'}:raise HTTPException(409,'Three explicit source coordinate texts are required; no unknown axis is set to zero.')
            if any(not r['can_accept'] for r in records):
                raise HTTPException(409,'Review the current source feature and its visual anchor before accepting these printed coordinates. Source unknowns remain unresolved.')
            fingerprint=inspection_fingerprint(p,records[0]['point_id'],records[0]['sheet_id'])
            if not fingerprint:raise HTTPException(409,'The source inspection changed; review this depiction before accepting XYZ.')
            try:tolerance=dimension_mm(body.tolerance_text)
            except ValueError as e:raise HTTPException(422,str(e)) from None
            if not 0<=tolerance<=Decimal('100000'):raise HTTPException(422,'Declare a finite supported source-coordinate tolerance.')
            model=prepare(p);ids={r['id'] for r in records};retained=[c for c in model['constraints'] if c['id'] not in ids]
            if len(retained)+3>MAX_CONSTRAINTS:raise HTTPException(409,'Dimensional constraint allowance reached.')
            for r in records:
                if abs(Decimal(r['proposed_value_mm']))>Decimal('1000000000000'):raise HTTPException(422,'Source coordinate exceeds the supported numerical range.')
                old=next((c for c in model['constraints'] if c['id']==r['id']),None)
                if old and old.get('verification')=='reviewed' and Decimal(old['value_mm'])!=Decimal(r['proposed_value_mm']):
                    raise HTTPException(409,'The previous accepted value differs from the printed proposal. Explicitly resolve that source constraint before replacing it.')
                for c in retained:
                    if c.get('kind')=='COORDINATE' and c.get('from_point_id')==r['point_id'] and c.get('sheet_id')==r['sheet_id'] and c.get('axis')==r['axis'] and c.get('verification')=='reviewed' and Decimal(c['value_mm'])!=Decimal(r['proposed_value_mm']):
                        raise HTTPException(409,'An accepted coordinate on this source differs. Resolve the conflict explicitly; source values were not moved.')
                retained.append({'id':r['id'],'kind':'COORDINATE','axis':r['axis'],'from_point_id':r['point_id'],'to_point_id':None,
                    'sheet_id':r['sheet_id'],'source_text':r['source_text'],'source_format':r['source_format'],'value_mm':r['proposed_value_mm'],
                    'tolerance_text':body.tolerance_text,'tolerance_mm':str(tolerance),'evidence':body.evidence,
                    'source_sha256':r['source_sha256'],'source_content_hash':deepcopy(r['source_content_hash']),
                    'verification':'reviewed','reviewed_by':actor['id'],'reviewed_at':api.now(),
                    'source_candidate_id':candidate_id,'source_proposal_id':r['id'],'source_inspection_sha256':fingerprint})
            model['constraints']=retained
        return api.change(project_id,body.version,actor,'Accepted three explicit printed XYZ source coordinates; stations and topology remain unchanged',update)
