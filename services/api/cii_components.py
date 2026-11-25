"""Explicit native component data entry; drafts and BEND contract gaps stay blocked."""
from copy import deepcopy
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt

from packages.workbooks.cii_components import component_report,save_record


class NativeComponentInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    kind:Literal['BEND','TEE','RIGID','RESTRAINT']
    component_id:str|None=Field(default=None,max_length=100)
    point_id:str|None=Field(default=None,max_length=100)
    element_id:str|None=Field(default=None,max_length=100)
    source_sheet_id:str|None=Field(default=None,max_length=100)
    review_state:Literal['DRAFT','REVIEWED']='DRAFT'
    values:dict[str,str|StrictInt|StrictBool|None]=Field(default_factory=dict,max_length=30)
    evidence:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]


class Withdrawal(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    reason:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]


def install(api):
    path='/api/v1/projects/{project_id}/cii-components'

    @api.app.get(path)
    def get(project_id:str,actor=Depends(api.user)):
        with api.db() as conn:p=api.project_read(project_id,actor,conn)
        return {**component_report(p),'revision':p['version'],'can_edit':actor['role'] in ('admin','engineer')}

    def save(project_id,record_id,body,actor):
        def update(p):
            try:save_record(p,body.model_dump(exclude={'version','confirmed'}),actor['id'],api.now(),record_id)
            except ValueError as error:raise HTTPException(422,str(error)) from None
        return api.change(project_id,body.version,actor,'Recorded explicit native component data; engineering/import approval not inferred',update)

    @api.app.post(path+'/records')
    def add(project_id:str,body:NativeComponentInput,actor=Depends(api.editor)):
        return save(project_id,None,body,actor)

    @api.app.patch(path+'/records/{record_id}')
    def edit(project_id:str,record_id:str,body:NativeComponentInput,actor=Depends(api.editor)):
        return save(project_id,record_id,body,actor)

    @api.app.delete(path+'/records/{record_id}')
    def remove(project_id:str,record_id:str,body:Withdrawal,actor=Depends(api.editor)):
        def update(p):
            if len(body.reason.strip())<10:raise HTTPException(422,'Describe why this native input is being withdrawn.')
            values=p.setdefault('analysis_model',{}).setdefault('native_components',[])
            target=next((r for r in values if r['id']==record_id),None)
            if not target:raise HTTPException(404,'Native component record not found.')
            p['analysis_model'].setdefault('native_component_history',[]).append({'record':deepcopy(target),
                'withdrawn_by':actor['id'],'withdrawn_at':api.now(),'reason':body.reason.strip()})
            values.remove(target)
        return api.change(project_id,body.version,actor,'Withdrew explicit native component input: '+body.reason,update)
