"""Explicit along-centreline station evidence and deliberate station application."""
from copy import deepcopy
from decimal import Decimal
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from packages.engineering import dimension_mm
from packages.engineering.coordinates import coordinate_value
from packages.physical.stations import (station_constraints,solve_stations,source_stamps,
    canonical_point_id,MAX_CONSTRAINTS,MAX_POINTS,SCHEMA)


class StationInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    kind:Literal['ABSOLUTE','DELTA','LOCAL_ORIGIN']
    from_point_id:str=Field(min_length=1,max_length=100)
    to_point_id:str|None=Field(default=None,max_length=100)
    source_text:str=Field(min_length=1,max_length=100)
    source_format:Literal['STANDARD','ISO_FT_IN_DOT_FRACTION','ISO_IN_DOT_FRACTION']='STANDARD'
    tolerance_text:str=Field(min_length=1,max_length=100)
    evidence:str=Field(min_length=10,max_length=3000)
    sheet_id:str=Field(min_length=1,max_length=100)
    confirmed:Literal[True]
    distance_basis:Literal['ALONG_CENTRELINE']
    source_proposal_id:str|None=Field(default=None,max_length=100)


class StationDecision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    reason:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]


class StationApply(StationDecision):
    point_ids:list[str]|None=Field(default=None,max_length=MAX_POINTS)


def scalar_value(source_text,source_format):
    parsed=coordinate_value(source_text,'X',source_format)
    if parsed['source_direction'] is not None:
        raise ValueError('Station evidence is a signed scalar along-centreline length/station, not an E/N/S/EL or XYZ coordinate.')
    return Decimal(parsed['value_mm'])


def _proposals(project):
    from packages.physical.source_review import station_source_proposals
    return station_source_proposals(project)


def install(api):
    @api.app.get('/api/v1/projects/{project_id}/physical-model/stations')
    def get(project_id:str,actor=Depends(api.user)):
        with api.db() as conn:p=api.project_read(project_id,actor,conn)
        return {'revision':p['version'],'constraints':station_constraints(p),'solution':solve_stations(p),
                'proposals':_proposals(p),'can_edit':actor['role'] in ('admin','engineer')}

    def save(project_id,constraint_id,body,actor):
        def update(p):
            model=p.setdefault('physical_model',{});constraints=model.setdefault('station_constraints',[])
            nodes={n['id']:n for n in p['nodes']}
            a=canonical_point_id(p,body.from_point_id);b=canonical_point_id(p,body.to_point_id) if body.to_point_id else None
            if a not in nodes or body.kind=='DELTA' and b not in nodes:raise HTTPException(422,'Select current physical source points.')
            if body.kind=='DELTA' and a==b:raise HTTPException(422,'An along-route delta needs two distinct physical points.')
            if body.kind!='DELTA' and b is not None:raise HTTPException(422,'An absolute station or declared local origin refers to exactly one physical point.')
            sheet=api.sheet_for(p,body.sheet_id)
            ids={a,b}-{None}
            if not any(any(i['sheet_id']==sheet['id'] for i in nodes[point]['instances']) for point in ids):
                raise HTTPException(422,'Select an actual source sheet depicting at least one referenced point.')
            try:
                value=scalar_value(body.source_text,body.source_format);tol=dimension_mm(body.tolerance_text)
            except ValueError as error:raise HTTPException(422,str(error)) from None
            if not value.is_finite() or value.copy_abs()>Decimal('1000000000000') or not 0<=tol<=100000:
                raise HTTPException(422,'Station value or declared tolerance is outside the supported physical range.')
            if value.as_tuple().exponent < -150 or tol.as_tuple().exponent < -150:
                raise HTTPException(422,'Station input exceeds the supported exact decimal precision.')
            if body.kind=='LOCAL_ORIGIN' and value!=0:
                raise HTTPException(422,'An explicitly chosen local origin must declare 0 mm. A missing station is never interpreted as zero.')
            if len(body.evidence.strip())<10:raise HTTPException(422,'Describe the actual engineering source or the deliberately chosen local datum.')
            proposal=None
            if body.source_proposal_id:
                proposal=next((v for v in _proposals(p) if v['id']==body.source_proposal_id),None)
                if not proposal:raise HTTPException(409,'Current source station-length proposal not found.')
                endpoints={canonical_point_id(p,proposal['from_point_id']),canonical_point_id(p,proposal['to_point_id'])}
                if body.kind!='DELTA' or {a,b}!=endpoints or proposal['sheet_id']!=sheet['id']:
                    raise HTTPException(422,'A source length proposal must retain its actual pair of endpoints and source drawing.')
                current=(proposal.get('source_content_hash')==sheet.get('content_hash') if proposal.get('source_content_hash') else proposal['source_sha256']==sheet['sha256'])
                if not current:raise HTTPException(409,'The proposed source length refers to changed drawing evidence.')
                if proposal.get('proposed_distance_mm') is None:
                    raise HTTPException(409,'The source length is not readable in the supported number convention; review the proposal before accepting it.')
                if value.copy_abs()!=Decimal(proposal['proposed_distance_mm']):
                    raise HTTPException(422,'The signed distance must retain the actual printed source length. Its direction is an explicit engineering decision, not a page measurement.')
            previous=next((c for c in constraints if c['id']==constraint_id),None)
            if constraint_id and not previous:raise HTTPException(404,'Station constraint not found.')
            if previous is None and len(constraints)>=MAX_CONSTRAINTS:raise HTTPException(409,'Station constraint allowance reached.')
            data={**body.model_dump(exclude={'version','confirmed'}),'id':constraint_id or api.uid(),
                'from_point_id':a,'to_point_id':b,'value_mm':str(value),'tolerance_mm':str(tol),
                'source_sha256':sheet['sha256'],'source_content_hash':deepcopy(sheet.get('content_hash')),
                'source_point_stamps':source_stamps(p,ids),'verification':'reviewed',
                'reviewed_by':actor['id'],'reviewed_at':api.now(),
                **({'source_proposal':deepcopy(proposal),'signed_direction_accepted':True} if proposal else {})}
            if previous:previous.clear();previous.update(data)
            else:constraints.append(data)
        return api.change(project_id,body.version,actor,'Accepted explicit along-centreline station evidence; stored stations were not moved',update)

    @api.app.post('/api/v1/projects/{project_id}/physical-model/stations/constraints')
    def add(project_id:str,body:StationInput,actor=Depends(api.editor)):
        return save(project_id,None,body,actor)

    @api.app.patch('/api/v1/projects/{project_id}/physical-model/stations/constraints/{constraint_id}')
    def edit(project_id:str,constraint_id:str,body:StationInput,actor=Depends(api.editor)):
        return save(project_id,constraint_id,body,actor)

    @api.app.delete('/api/v1/projects/{project_id}/physical-model/stations/constraints/{constraint_id}')
    def remove(project_id:str,constraint_id:str,body:StationDecision,actor=Depends(api.editor)):
        def update(p):
            constraints=p.setdefault('physical_model',{}).setdefault('station_constraints',[])
            target=next((c for c in constraints if c['id']==constraint_id),None)
            if not target:raise HTTPException(404,'Station constraint not found.')
            if len(body.reason.strip())<10:raise HTTPException(422,'Describe why this source constraint is being withdrawn.')
            p['physical_model'].setdefault('retired_station_constraints',[]).append({
                'constraint':deepcopy(target),'reason':body.reason,'withdrawn_by':actor['id'],'withdrawn_at':api.now()})
            constraints.remove(target)
        return api.change(project_id,body.version,actor,'Withdrew along-centreline station source evidence: '+body.reason,update)

    @api.app.post('/api/v1/projects/{project_id}/physical-model/stations/apply')
    def apply(project_id:str,body:StationApply,actor=Depends(api.editor)):
        def update(p):
            if len(body.reason.strip())<10:raise HTTPException(422,'Describe the station solution being explicitly accepted.')
            solution=solve_stations(p);rows={r['point_id']:r for r in solution['points']};nodes={n['id']:n for n in p['nodes']}
            requested={canonical_point_id(p,v) for v in body.point_ids} if body.point_ids is not None else {r['point_id'] for r in rows.values() if r['can_apply']}
            if not requested:raise HTTPException(409,'No fully anchored, source-current station solution is ready. Unknown datums remain unknown.')
            if any(point not in rows or not rows[point]['can_apply'] for point in requested):
                raise HTTPException(409,'Every selected point needs an explicitly assigned route and a source-current anchored station solution. No partial selection was applied.')
            groups=p.setdefault('physical_model',{}).setdefault('station_evidence_groups',{})
            for point in requested:
                row=rows[point];node=nodes[point];previous=node.get('station_proof')
                if previous and (previous.get('input_sha256')!=row['input_sha256'] or previous.get('value_mm')!=row['station_mm']):
                    node.setdefault('station_proof_history',[]).append(deepcopy(previous))
                if node.get('station_mm') is not None and node.get('station_mm')!=row['station_mm']:
                    node.setdefault('station_history',[]).append({k:deepcopy(node.get(k)) for k in ('station_mm','dimension_input','evidence','station_proof','manual_station_basis')})
                groups[row['constraint_group_id']]=deepcopy(solution['evidence_groups'][row['constraint_group_id']])
                keep_manual=deepcopy(row.get('retained_manual_anchor'))
                node['station_mm']=row['station_mm']
                if keep_manual is None:
                    node.update(dimension_input=row['station_mm']+' mm',evidence=body.reason)
                node['station_proof']={'schema':SCHEMA,'value_mm':row['station_mm'],'basis':row['basis'],
                    'basis_id':row['basis_id'],'basis_point_id':row['basis_point_id'],'line_id':node['line_id'],'route':node['route'],
                    'constraint_ids':row['constraint_ids'],'constraint_group_id':row['constraint_group_id'],
                    'constraint_ids_complete':row['constraint_ids_complete'],'accepted_revision':p['version']+1,'input_sha256':row['input_sha256'],
                    'solution_input_sha256':solution['input_sha256'],'tolerance_mm':row['tolerance_mm'],
                    'retained_manual_anchor':keep_manual,'evidence':body.reason,'reviewed_by':actor['id'],'reviewed_at':api.now()}
                node.pop('manual_station_basis',None)
        return api.change(project_id,body.version,actor,'Explicitly accepted anchored along-centreline station solution; no XYZ/page lengths inferred',update)
