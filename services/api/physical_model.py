"""Evidence-backed component interfaces and explicit signed source dimensions."""
from copy import deepcopy
from decimal import Decimal
from typing import Annotated,Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from packages.engineering import dimension_mm
from packages.engineering.coordinates import coordinate_value
from packages.physical import POLICIES,prepare,audit
from packages.physical.constraints import solve,MAX_CONSTRAINTS
from packages.physical.cod import proposals as cod_proposals,CONVENTION
from packages.automation.recognize import identity

Coordinate=Annotated[float,Field(ge=0,le=14400,allow_inf_nan=False)]
class PortInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    point_id:str
    sheet_id:str
    bbox:tuple[Coordinate,Coordinate,Coordinate,Coordinate]
    evidence:str=Field(min_length=10,max_length=3000)
    dimension_convention:str=Field(default='',max_length=1000)

class ComponentInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    kind:Literal['flange','valve','inline_instrument','single_instrument','instrument_unclassified','tee','elbow','support']
    ports:dict[str,PortInput|None]=Field(max_length=3)
    evidence:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]
    cod_convention_confirmed:bool=False

class DimensionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    kind:Literal['DELTA','COORDINATE']
    axis:Literal['X','Y','Z']
    from_point_id:str
    to_point_id:str|None=None
    source_text:str=Field(min_length=1,max_length=100)
    source_format:Literal['STANDARD','ISO_FT_IN_DOT_FRACTION']='STANDARD'
    tolerance_text:str=Field(default='0 mm',max_length=100)
    sheet_id:str
    evidence:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]

class Decision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    reason:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]


def install(api):
    @api.app.get('/api/v1/projects/{project_id}/physical-model')
    def get(project_id:str,actor=Depends(api.user)):
        with api.db() as conn:p=api.project_read(project_id,actor,conn)
        return {'revision':p['version'],**audit(p),'dimensions':p.get('physical_model',{}).get('constraints',[]),
                'solution':solve(p),'cod_proposals':cod_proposals(p),'policies':POLICIES,'can_edit':actor['role'] in ('admin','engineer')}

    @api.app.post('/api/v1/projects/{project_id}/physical-model/components/{component_id}/accept-cod')
    def accept_cod(project_id:str,component_id:str,body:Decision,actor=Depends(api.editor)):
        def update(p):
            model=prepare(p)
            proposal=next((c for c in cod_proposals(p) if c['component_id']==component_id),None)
            if not proposal or proposal['status'] not in ('COD_PROPOSED','COD_ACCEPTED'):
                raise HTTPException(409,'COD is not sufficiently constrained by current engineering leg coordinates and the confirmed source convention. Unknowns or conflicts remain unresolved.')
            retained=[c for c in model['constraints'] if c.get('cod_derivation',{}).get('component_id')!=component_id]
            if len(retained)+3>MAX_CONSTRAINTS:raise HTTPException(409,'Dimensional constraint allowance reached.')
            sheet=api.sheet_for(p,proposal['source_sheet_id'])
            for axis,value in proposal['coordinates_mm'].items():
                retained.append({'id':identity(p['id'],component_id,'cod',axis),'kind':'COORDINATE','axis':axis,
                    'from_point_id':proposal['point_id'],'to_point_id':None,'source_text':f'Derived theoretical COD {axis}: {value} mm',
                    'value_mm':value,'tolerance_mm':'0','tolerance_text':'0 mm','sheet_id':sheet['id'],
                    'source_sha256':sheet['sha256'],'source_content_hash':sheet.get('content_hash'),
                    'evidence':body.reason,'verification':'reviewed','reviewed_by':actor['id'],'reviewed_at':api.now(),
                    'cod_derivation':deepcopy(proposal['derivation'])})
            model['constraints']=retained
        return api.change(project_id,body.version,actor,'Accepted exact dimension-chain theoretical COD; route stations and bend radius not inferred',update)

    @api.app.patch('/api/v1/projects/{project_id}/physical-model/components/{component_id}')
    def component(project_id:str,component_id:str,body:ComponentInput,actor=Depends(api.editor)):
        def update(p):
            model=prepare(p);target=next((c for c in model['components'] if c['id']==component_id),None)
            if not target:raise HTTPException(404,'Current component occurrence not found.')
            allowed={'inline_instrument','single_instrument','instrument_unclassified'} if target['family']=='instrument' else {target['family']}
            if body.kind not in allowed:raise HTTPException(422,'Correct the material family first; this occurrence cannot silently change component family.')
            policy=POLICIES[body.kind]
            if set(body.ports)-set(policy['ports']):raise HTTPException(422,'This component has unsupported process connections. A single-ended PIT has only one process port.')
            associations={}
            for key,kind in zip(policy['ports'],policy['proof']):
                port=body.ports.get(key)
                if port is None:associations[key]=None;continue
                node=next((n for n in p['nodes'] if n['id']==port.point_id),None)
                if not node or node['line_id']!=target['line_id']:raise HTTPException(422,'Choose an existing physical point on the component’s full line ID.')
                sheet=api.sheet_for(p,port.sheet_id)
                instance=next((v for v in node['instances'] if v['sheet_id']==sheet['id']),None)
                x0,y0,x1,y1=port.bbox
                if (not instance or not 0<=x0<x1<=sheet['width'] or not 0<=y0<y1<=sheet['height'] or
                    not x0<=instance['anchor'][0]<=x1 or not y0<=instance['anchor'][1]<=y1):
                    raise HTTPException(422,'Source proof must enclose that point’s anchor within its actual unrotated source page.')
                if body.kind=='tee' and (node['kind']!='tee' or node['route']!='main'):
                    raise HTTPException(422,'Select the existing common main-run tee point; a separate branch tee identity is forbidden.')
                if body.kind=='elbow' and len(port.dimension_convention.strip())<10:
                    raise HTTPException(422,'State the engineering dimension convention proving theoretical COD; diagram angles are not dimensional evidence.')
                associations[key]={'point_id':node['id'],'proof':{
                    'kind':kind,'sheet_id':sheet['id'],'source_sha256':sheet['sha256'],
                    'content_hash':sheet.get('content_hash'),'bbox':list(port.bbox),
                    'evidence':port.evidence,'dimension_convention':port.dimension_convention,
                    'reviewed_by':actor['id'],'reviewed_at':api.now()}}
                if body.kind=='elbow' and body.cod_convention_confirmed:
                    associations[key]['proof']['dimension_convention_kind']=CONVENTION
            points=[next(n for n in p['nodes'] if n['id']==a['point_id']) for a in associations.values() if a]
            if len(points)==2:
                a,b=points
                if a['id']==b['id'] or (a['route']==b['route'] and a.get('station_mm') is not None and b.get('station_mm') is not None and Decimal(a['station_mm'])==Decimal(b['station_mm'])):
                    raise HTTPException(422,'Opposite process ends require distinct physical stations. Both flange nodes cannot occupy the same face.')
            target.update(kind=body.kind,ports=associations,evidence=body.evidence,
                          verification='reviewed',reviewed_by=actor['id'],reviewed_at=api.now())
            material=next(m for m in p['materials'] if m['id']==target['material_id'])
            related=[c for c in model['components'] if c['material_id']==material['id']]
            material['observed']=sum(bool(c['ports']) and c.get('verification')=='reviewed' and all(c['ports'].values()) for c in related)
            material['observed_source']='physical-port-mappings';p['materials_reviewed']=False;p['layout_reviewed']=False
            prepare(p)
        return api.change(project_id,body.version,actor,'Reviewed component physical interfaces and source associations',update)

    def save_dimension(project_id,dimension_id,body,actor):
        def update(p):
            model=prepare(p);nodes={n['id']:n for n in p['nodes']}
            if body.from_point_id not in nodes or (body.kind=='DELTA' and body.to_point_id not in nodes):raise HTTPException(422,'Select active physical points.')
            if body.kind=='DELTA' and body.from_point_id==body.to_point_id:raise HTTPException(422,'A signed delta requires two different physical points.')
            if body.kind=='COORDINATE' and body.to_point_id is not None:raise HTTPException(422,'An absolute coordinate refers to one physical point.')
            sheet=api.sheet_for(p,body.sheet_id)
            ids={body.from_point_id,body.to_point_id}-{None}
            if not any(any(v['sheet_id']==sheet['id'] for v in nodes[n]['instances']) for n in ids):
                raise HTTPException(422,'Select a source sheet depicting at least one referenced point.')
            try:
                parsed=coordinate_value(body.source_text,body.axis,body.source_format)
                value=Decimal(parsed['value_mm']);tolerance=dimension_mm(body.tolerance_text)
            except ValueError as error:raise HTTPException(422,str(error)) from None
            if value.copy_abs()>Decimal('1000000000000') or not 0<=tolerance<=Decimal('100000'):
                raise HTTPException(422,'Dimension or explicit tolerance is outside the supported range.')
            previous=next((c for c in model['constraints'] if c['id']==dimension_id),None)
            if dimension_id and not previous:raise HTTPException(404,'Dimensional constraint not found.')
            if not previous and len(model['constraints'])>=MAX_CONSTRAINTS:raise HTTPException(409,'Dimensional constraint allowance reached.')
            data={**body.model_dump(exclude={'version','confirmed'}),'id':dimension_id or api.uid(),
                  'value_mm':str(value),'tolerance_mm':str(tolerance),'source_sha256':sheet['sha256'],
                  'source_direction':parsed['source_direction'],
                  'source_content_hash':sheet.get('content_hash'),'verification':'reviewed',
                  'reviewed_by':actor['id'],'reviewed_at':api.now()}
            if previous:previous.clear();previous.update(data)
            else:model['constraints'].append(data)
        return api.change(project_id,body.version,actor,'Reviewed signed engineering dimension and source proof',update)

    @api.app.post('/api/v1/projects/{project_id}/physical-model/dimensions')
    def add_dimension(project_id:str,body:DimensionInput,actor=Depends(api.editor)):
        return save_dimension(project_id,None,body,actor)

    @api.app.patch('/api/v1/projects/{project_id}/physical-model/dimensions/{dimension_id}')
    def edit_dimension(project_id:str,dimension_id:str,body:DimensionInput,actor=Depends(api.editor)):
        return save_dimension(project_id,dimension_id,body,actor)

    @api.app.delete('/api/v1/projects/{project_id}/physical-model/dimensions/{dimension_id}')
    def remove_dimension(project_id:str,dimension_id:str,body:Decision,actor=Depends(api.editor)):
        def update(p):
            model=prepare(p);before=len(model['constraints'])
            model['constraints']=[c for c in model['constraints'] if c['id']!=dimension_id]
            if len(model['constraints'])==before:raise HTTPException(404,'Dimensional constraint not found.')
        return api.change(project_id,body.version,actor,'Removed source dimension from active model: '+body.reason,update)

    @api.app.post('/api/v1/projects/{project_id}/physical-model/apply-vectors')
    def apply_vectors(project_id:str,body:Decision,actor=Depends(api.editor)):
        def update(p):
            solution=solve(p)
            if any(i['code']!='DIMENSION_SOLUTION_STALE' for i in solution['issues']):
                raise HTTPException(409,'Resolve conflicting, stale-source or unsupported dimensional constraints before accepting vectors.')
            complete=[e for e in solution['elements'] if all(v is not None for v in e['delta_mm'].values())]
            if not complete:raise HTTPException(409,'No complete signed XYZ element vectors are currently proved. Unknown axes remain blank.')
            stored=p.setdefault('analysis_model',{}).setdefault('elements',[]);by_id={e['id']:e for e in stored}
            for edge in complete:
                uid=identity(p['id'],edge['from'],edge['to']);data=deepcopy(by_id.get(uid,{}))
                retained=deepcopy(data.get('geometry_source_inputs',[])) if data.get('geometry_origin')=='constraint-solution' else [deepcopy(c) for c in solution['inputs'] if c.get('source')=='analysis-element' and c['id'].startswith(uid+':')]
                data.update(id=uid,from_point_id=edge['from'],to_point_id=edge['to'],
                    **{'d'+axis.lower()+'_mm':value for axis,value in edge['delta_mm'].items()},
                    geometry_origin='constraint-solution',geometry_source_sha256=solution['input_sha256'],
                    geometry_source_inputs=retained,
                    geometry_evidence_groups=edge['evidence_groups'],verification='engineer-entered',
                    evidence=body.reason,entered_by=actor['id'])
                stored[:]=[e for e in stored if e['id']!=uid]+[data]
        return api.change(project_id,body.version,actor,'Accepted proved signed XYZ vectors; stations and pipe properties retained',update)
