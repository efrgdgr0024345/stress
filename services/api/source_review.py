"""Prepare source-located blue review points without accepting topology."""
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from packages.physical.source_review import prepare_source_points


class PrepareInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    confirmed:Literal[True]


def install(api):
    @api.app.post('/api/v1/projects/{project_id}/physical-model/source-points')
    def source_points(project_id:str,body:PrepareInput,actor=Depends(api.editor)):
        def update(p):
            try:prepare_source_points(p)
            except ValueError as error:raise HTTPException(409,str(error)) from None
            from packages.engineering.graph_review import renumber_project
            renumber_project(p,'Registered complete provisional source-point numbering map',actor['id'],api.now())
            p['layout_reviewed']=False
        return api.change(project_id,body.version,actor,'Prepared source-located provisional physical interfaces; no topology, station or engineering approval inferred',update)
