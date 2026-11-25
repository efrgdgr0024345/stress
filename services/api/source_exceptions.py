"""Source-bound exception history; recording an explanation never approves facts."""
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from packages.physical.source_exceptions import source_exception_report,record_source_exception_decision


class SourceExceptionDecision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    exception_id:str=Field(min_length=1,max_length=100)
    decision:Literal['CONFIRM_WITNESS_MAPPING','REOPEN','RETAIN_UNRESOLVED']
    evidence:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]
    constraint_ids:list[str]=Field(default_factory=list,max_length=1)
    source_context_sha256:str=Field(min_length=64,max_length=64)


def install(api):
    @api.app.get('/api/v1/projects/{project_id}/physical-model/source-exceptions')
    def get(project_id:str,actor=Depends(api.user)):
        with api.db() as conn:p=api.project_read(project_id,actor,conn)
        from packages.physical.stations import station_constraints
        return {'revision':p['version'],'can_edit':actor['role'] in ('admin','engineer'),
                **source_exception_report(p),'station_constraints':station_constraints(p)}

    @api.app.post('/api/v1/projects/{project_id}/physical-model/source-exceptions/decision')
    def decide(project_id:str,body:SourceExceptionDecision,actor=Depends(api.editor)):
        def update(p):
            try:record_source_exception_decision(p,body.exception_id,body.decision,body.evidence,
                    actor['id'],api.now(),constraint_ids=body.constraint_ids,source_context_sha256=body.source_context_sha256)
            except ValueError as error:raise HTTPException(422,str(error)) from None
        return api.change(project_id,body.version,actor,'Recorded source exception review: '+body.decision,update)
