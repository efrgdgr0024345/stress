"""Preview then atomically accept explicit route decisions; never infer topology."""
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field

from packages.engineering.graph_review import (MAX_POINTS,audit_graph,point_rows,
    preview_topology,apply_topology)


class Assignment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    point_id:str=Field(min_length=1,max_length=100)
    topology_state:Literal['ASSIGNED','UNASSIGNED']
    line_id:str=Field(min_length=1,max_length=150)
    route:str|None=Field(default=None,pattern=r'^(main|branch-\d{2})$')
    order:int|None=Field(default=None,ge=0,le=100000,strict=True)
    takeoff_id:str|None=Field(default=None,max_length=100)
    topology_confirmed:bool=False


class TopologyPreview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    assignments:list[Assignment]=Field(default_factory=list,max_length=MAX_POINTS)
    reason:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]


class TopologyApply(TopologyPreview):
    preview_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


def install(api):
    path='/api/v1/projects/{project_id}/topology-review'

    @api.app.get(path)
    def get(project_id:str,actor=Depends(api.user)):
        with api.db() as conn:p=api.project_read(project_id,actor,conn)
        return {**audit_graph(p),'revision':p['version'],
            'can_edit':actor['role'] in ('admin','engineer'),'points':point_rows(p),
            'numbering_map':p.get('numbering_map',[]),'numbering_history':p.get('numbering_history',[])}

    @api.app.post(path+'/preview')
    def preview(project_id:str,body:TopologyPreview,actor=Depends(api.editor)):
        with api.db() as conn:p=api.project_read(project_id,actor,conn)
        if p['version']!=body.version:raise HTTPException(409,'The project changed; reload before previewing topology.')
        try:return preview_topology(p,[r.model_dump() for r in body.assignments],body.reason)
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @api.app.post(path+'/apply')
    def apply(project_id:str,body:TopologyApply,actor=Depends(api.editor)):
        def update(p):
            try:apply_topology(p,[r.model_dump() for r in body.assignments],body.reason,
                body.preview_sha256,actor['id'],api.now())
            except ValueError as error:raise HTTPException(422,str(error)) from None
            p['layout_reviewed']=False
        return api.change(project_id,body.version,actor,'Applied explicit source-inspected topology and deterministic numbering',update)
