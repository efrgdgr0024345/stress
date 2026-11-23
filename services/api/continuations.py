"""Reviewed cross-sheet identity, with source-bound coordinate comparison."""
from copy import deepcopy
from decimal import Decimal
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from packages.engineering import dimension_mm
from packages.engineering.continuations import assess_pair,source_stamp,merge_identity,coordinate_proof,audit,LIMIT
from packages.physical.constraints import observations,solve


class MatchInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    left_point_id:str=Field(max_length=100)
    right_point_id:str=Field(max_length=100)
    left_size:str=Field(min_length=1,max_length=40)
    right_size:str=Field(min_length=1,max_length=40)
    tolerance_text:str=Field(default='0.01 mm',max_length=100)
    decision:Literal['PROPOSE','ACCEPT_IDENTITY','REJECT']='PROPOSE'
    topology_confirmed:bool=False
    evidence:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]
    left_candidate_id:str|None=Field(default=None,max_length=100)
    right_candidate_id:str|None=Field(default=None,max_length=100)


class ReviewInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    decision:Literal['WITHDRAW','REVALIDATE']
    topology_confirmed:bool=False
    evidence:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]


def install(api):
    @api.app.patch('/api/v1/projects/{project_id}/continuations/{link_id}')
    def review(project_id:str,link_id:str,body:ReviewInput,actor=Depends(api.editor)):
        def update(p):
            link=next((v for v in p.get('continuations',[]) if v['id']==link_id),None)
            if not link:raise HTTPException(404,'Continuation review not found.')
            if link['status'] in ('SUPERSEDED','REJECTED'):raise HTTPException(409,'That historical decision is retained. Review a current connection instead.')
            if body.decision=='WITHDRAW':link['status']='WITHDRAWN'
            else:
                point=link.get('point_id');node=next((n for n in p['nodes'] if n['id']==point),None)
                if not node or not body.topology_confirmed:raise HTTPException(422,'Confirm the current shared physical interface and topology.')
                source_sheets={v['sheet_id'] for v in node['instances']}
                if len(source_sheets)<2:raise HTTPException(409,'A shared continuation needs two or more source depictions.')
                for sheet_id in source_sheets:
                    sheet=api.sheet_for(p,sheet_id)
                    if not sheet.get('identity_verified') or sheet['line_id']!=link['line_id']:raise HTTPException(409,'Confirm current source sheet and full line identities.')
                inputs=observations(p)
                for axis in ('X','Y','Z'):
                    values=[]
                    for sheet in source_sheets:
                        axis_values=[Decimal(c['value_mm']) for c in inputs if c['kind']=='COORDINATE' and c['axis']==axis and c['from_point_id']==point and c.get('sheet_id')==sheet]
                        if not axis_values:raise HTTPException(409,'Revalidation needs independent accepted XYZ coordinates on every depicting source sheet. Unknowns remain unresolved.')
                        values.extend(axis_values)
                    if any(v!=values[0] for v in values):raise HTTPException(409,'Independent source coordinates differ; preserve them and resolve the discrepancy before revalidation.')
                if any(set(i.get('point_ids',[]))&{point} for i in solve(p)['issues']):raise HTTPException(409,'Resolve conflicting dimensional inputs before revalidation.')
                link.update(status='ACCEPTED',source_stamps=source_stamp(p,{point}),coordinate_proof_sha256=coordinate_proof(p,{point}))
            link.update(evidence=body.evidence,reviewed_by=actor['id'],reviewed_at=api.now())
            p['layout_reviewed']=False
        return api.change(project_id,body.version,actor,'Reviewed existing continuation proof / withdrawal',update)

    @api.app.get('/api/v1/projects/{project_id}/continuations')
    def get(project_id:str,actor=Depends(api.user)):
        with api.db() as conn:p=api.project_read(project_id,actor,conn)
        return {'revision':p['version'],'links':p.get('continuations',[]),'issues':audit(p),
                'candidates':p.get('automation',{}).get('continuation_candidates',[]),
                'candidate_pairs':p.get('automation',{}).get('continuation_pairs',[]),
                'can_edit':actor['role'] in ('admin','engineer')}

    @api.app.post('/api/v1/projects/{project_id}/continuations')
    def compare(project_id:str,body:MatchInput,actor=Depends(api.editor)):
        def update(p):
            links=p.setdefault('continuations',[])
            if len(links)>=LIMIT:raise HTTPException(409,'Continuation review allowance reached.')
            try:
                tolerance=dimension_mm(body.tolerance_text)
                state=assess_pair(p,body.left_point_id,body.right_point_id,body.left_size,body.right_size,str(tolerance))
            except ValueError as error:raise HTTPException(422,str(error)) from None
            stamps=source_stamp(p,{body.left_point_id,body.right_point_id})
            relation={**state,'id':api.uid(),'source_stamps':stamps,'evidence':body.evidence,
                      'reviewed_by':actor['id'],'reviewed_at':api.now(),'topology_confirmed':body.topology_confirmed}
            candidates={c['id']:c for c in p.get('automation',{}).get('continuation_candidates',[])}
            source_ids=[]
            for cid,pid in ((body.left_candidate_id,body.left_point_id),(body.right_candidate_id,body.right_point_id)):
                if not cid:continue
                candidate=candidates.get(cid);point=next(n for n in p['nodes'] if n['id']==pid)
                if not candidate or candidate['sheet_id'] not in {v['sheet_id'] for v in point['instances']}:
                    raise HTTPException(422,'A continuation source reference must appear on the selected point’s actual sheet.')
                source_ids.append(cid)
            relation['source_candidate_ids']=source_ids
            for previous in links:
                previous_pair={p.get('point_aliases',{}).get(v,v) for v in (previous['left_point_id'],previous['right_point_id'])}
                if previous['status'] not in ('ACCEPTED','REJECTED','SUPERSEDED') and previous_pair=={body.left_point_id,body.right_point_id}:
                    previous['status']='SUPERSEDED'
            if body.decision=='REJECT':relation.update(status='REJECTED',rejection_status=state['status'])
            elif body.decision=='ACCEPT_IDENTITY':
                if state['status']!='EXACT_COORDINATE_MATCH':
                    raise HTTPException(409,'The source coordinates are not proved identical. Save a proposal to retain per-axis discrepancies; source values are never silently moved.')
                if not body.topology_confirmed:raise HTTPException(422,'Explicitly confirm component/interface identity and topology, not only equal coordinates.')
                for stamp in stamps:
                    sheet=api.sheet_for(p,stamp['sheet_id'])
                    if not sheet.get('identity_verified') or sheet['line_id']!=state['line_id']:
                        raise HTTPException(409,'Confirm the printed sheet and full line identities before unifying physical points.')
                # A copy ensures that validation errors never leave a partly
                # rewired object for callers or future update operations.
                working=deepcopy(p)
                inherited={cid for previous in links if previous['status']=='ACCEPTED' and previous.get('point_id') in (body.left_point_id,body.right_point_id)
                           for cid in previous.get('source_candidate_ids',[])}
                try:keep=merge_identity(working,body.left_point_id,body.right_point_id)
                except ValueError as error:raise HTTPException(409,str(error)) from None
                solution=solve(working)
                canonical=next((c for c in solution['coordinates'] if c['point_id']==keep['id']),None)
                if not canonical or any(v['value_mm'] is None for v in canonical['axes'].values()) or any(
                    i['code']=='COD_SOURCE_STALE' and keep['id'] in i.get('point_ids',[]) for i in solution['issues']):
                    raise HTTPException(409,'Merging would invalidate a coordinate derivation. Reconcile the source proof before sharing this identity.')
                relation.update(status='ACCEPTED',point_id=keep['id'],
                    source_candidate_ids=sorted(set(source_ids)|inherited),
                    coordinate_proof_sha256=coordinate_proof(working,{keep['id']}))
                p.clear();p.update(working);links=p.setdefault('continuations',[])
            links.append(relation)
            p['layout_reviewed']=False
        return api.change(project_id,body.version,actor,'Reviewed cross-sheet continuation identity and source coordinate deltas',update)
