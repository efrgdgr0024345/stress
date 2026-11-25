"""Reviewed cross-sheet identity, with source-bound coordinate comparison."""
from copy import deepcopy
import re
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from packages.engineering import dimension_mm
from packages.engineering.continuations import (assess_pair,source_stamp,merge_identity,coordinate_proof,audit,LIMIT,
    make_source_review,source_review_records,source_review_states,candidate_point_id,SOURCE_REVIEW_LIMIT,
    independent_source_coordinates,_source_observations,source_binding)
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


class SourceDecisionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)
    decision:Literal['REJECT_MATCH','DECLARE_EXTERNAL_BOUNDARY','REOPEN']
    reason_code:Literal['MISSING_PEER_IN_PACK','EQUIPMENT_BOUNDARY','ACCEPTED_XYZ_REQUIRED',
                        'SOURCE_INTERFACE_UNCONFIRMED','LINE_OR_SIZE_MISMATCH']
    evidence:str=Field(min_length=10,max_length=3000)
    confirmed:Literal[True]


def source_locations_current(project,node):
    from packages.engineering import source_location_reviewed
    sheets={s['id']:s for s in project['sheets']}
    return all(source_location_reviewed({**node,'source_observation':observation},sheets)
               for observation in _source_observations(node))


def candidate_compatible(project,candidate,point,peer,declared_size):
    """Curated references identify an actual interface, not just a sheet."""
    canonical=candidate_point_id(project,candidate)
    if not source_binding(project,candidate)['source_current']:
        raise HTTPException(409,'This source reference changed or is unavailable; refresh its evidence before matching.')
    if canonical and canonical!=point['id']:
        raise HTTPException(422,'This continuation label refers to a different physical source interface on the sheet.')
    if candidate['sheet_id'] not in {i['sheet_id'] for i in point['instances']}:
        raise HTTPException(422,'A continuation source reference must appear on the selected point’s actual sheet.')
    if canonical and candidate.get('anchor'):
        instance=next(i for i in point['instances'] if i['sheet_id']==candidate['sheet_id'])
        if list(instance['anchor'])!=list(candidate['anchor']):
            from packages.engineering import source_location_reviewed
            sheets={s['id']:s for s in project['sheets']}
            if not source_location_reviewed(point,sheets,candidate['sheet_id']):
                raise HTTPException(409,'The curated proposal anchor differs from the current point. Explicitly re-inspect this same source interface before matching it.')
    if candidate.get('target_kind')=='EXTERNAL_EQUIPMENT':
        raise HTTPException(409,'This reference targets external equipment. A separately proved equipment/nozzle interface is required; an internal piping peer was not identified.')
    target=candidate.get('target_line_proposal')
    if target and target.upper()!=peer['line_id'].upper():
        raise HTTPException(409,'The printed reference targets another full line; reject it or declare an external boundary instead of sharing this identity.')
    if candidate.get('target_printed_sheet') is not None:
        def printed(sheet):
            match=re.search(r'(?:\bSHEET\s*)?(\d+)\s*(?:OF|/)\s*\d+|^\s*(\d+)\s*$',sheet.get('printed_id',''),re.I)
            return int(next(v for v in match.groups() if v)) if match else None
        sheets={s['id']:s for s in project['sheets']}
        if not any(printed(sheets[i['sheet_id']])==candidate['target_printed_sheet'] for i in peer['instances']):
            raise HTTPException(409,'The other depiction is not on the printed target sheet. Page index is not sheet identity.')
    size=candidate.get('nominal_size') or candidate.get('size') or candidate.get('nominal_size_proposal',{}).get('nps_inches_text')
    if size:
        from packages.engineering.continuations import size_value
        try:matching=size_value(str(size))==size_value(declared_size)
        except ValueError:matching=False
        if not matching:raise HTTPException(409,'The declared nominal size conflicts with this source-reference size.')


def install(api):
    @api.app.post('/api/v1/projects/{project_id}/continuations/sources/{candidate_id}/decision')
    def source_decision(project_id:str,candidate_id:str,body:SourceDecisionInput,actor=Depends(api.editor)):
        def update(p):
            candidate=next((c for c in p.get('automation',{}).get('continuation_candidates',[]) if c['id']==candidate_id),None)
            if not candidate:raise HTTPException(404,'Current continuation source reference not found.')
            records=p.setdefault('continuation_source_reviews',[])
            if len(records)>=SOURCE_REVIEW_LIMIT:raise HTTPException(409,'Continuation source review allowance reached.')
            accepted=[link for link in p.get('continuations',[]) if link['status']=='ACCEPTED' and candidate_id in link.get('source_candidate_ids',[])]
            if accepted and body.decision!='REOPEN':
                raise HTTPException(409,'Reopen or withdraw the existing shared-identity approval before declaring an endpoint exception or external boundary.')
            for link in accepted:
                link.update(status='WITHDRAWN',evidence=body.evidence,reviewed_by=actor['id'],reviewed_at=api.now())
            try:record=make_source_review(p,candidate,body.decision,body.reason_code,body.evidence,actor['id'],api.now())
            except ValueError as error:raise HTTPException(409,str(error)) from None
            previous=next((r for r in reversed(records) if r['candidate_id']==candidate_id),None)
            if previous:record['supersedes_id']=previous['id']
            records.append(record)
            p['layout_reviewed']=False
        return api.change(project_id,body.version,actor,'Reviewed continuation source endpoint disposition; no peer identity or engineering approval inferred',update)

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
                if not source_locations_current(p,node):raise HTTPException(409,'Review each source depiction’s current location before revalidating shared identity.')
                source_sheets={v['sheet_id'] for v in node['instances']}
                if len(source_sheets)<2:raise HTTPException(409,'A shared continuation needs two or more source depictions.')
                for sheet_id in source_sheets:
                    sheet=api.sheet_for(p,sheet_id)
                    if not sheet.get('identity_verified') or sheet['line_id']!=link['line_id']:raise HTTPException(409,'Confirm current source sheet and full line identities.')
                direct=independent_source_coordinates(p,node)
                if direct['missing'] or direct['conflicting_axes']:raise HTTPException(409,'Revalidation needs exact independent direct accepted XYZ coordinates on every depicting source sheet. Unknowns or differences remain unresolved.')
                if any(set(i.get('point_ids',[]))&{point} for i in solve(p)['issues']):raise HTTPException(409,'Resolve conflicting dimensional inputs before revalidation.')
                link.update(status='ACCEPTED',source_stamps=source_stamp(p,{point}),coordinate_proof_sha256=coordinate_proof(p,{point}))
            link.update(evidence=body.evidence,reviewed_by=actor['id'],reviewed_at=api.now())
            p['layout_reviewed']=False
        return api.change(project_id,body.version,actor,'Reviewed existing continuation proof / withdrawal',update)

    @api.app.get('/api/v1/projects/{project_id}/continuations')
    def get(project_id:str,actor=Depends(api.user)):
        with api.db() as conn:p=api.project_read(project_id,actor,conn)
        states=source_review_states(p)
        candidates=[{**deepcopy(c),'point_id':states[c['id']]['point_id']} for c in p.get('automation',{}).get('continuation_candidates',[])]
        return {'revision':p['version'],'links':p.get('continuations',[]),'issues':audit(p),
                'candidates':candidates,'source_reviews':source_review_records(p),'source_review_states':states,
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
            from packages.engineering.continuations import identity_audit
            invalid_links={i['continuation_id'] for i in identity_audit(p)}
            for cid,pid in ((body.left_candidate_id,body.left_point_id),(body.right_candidate_id,body.right_point_id)):
                bound={c['id'] for c in candidates.values() if c.get('origin')=='source-review-profile' and candidate_point_id(p,c)==pid}
                inherited={source_id for link in links if link['status']=='ACCEPTED' and link['id'] not in invalid_links and link.get('point_id')==pid
                           for source_id in link.get('source_candidate_ids',[])}
                if bound-inherited-({cid} if cid else set()):
                    raise HTTPException(422,'Choose this physical point’s actual curated continuation source reference; its printed target context cannot be bypassed.')
                if not cid:continue
                candidate=candidates.get(cid);point=next(n for n in p['nodes'] if n['id']==pid)
                if not candidate:raise HTTPException(422,'Continuation source reference not found.')
                peer=next(n for n in p['nodes'] if n['id']==(body.right_point_id if pid==body.left_point_id else body.left_point_id))
                candidate_compatible(p,candidate,point,peer,body.left_size if pid==body.left_point_id else body.right_size)
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
                if not all(source_locations_current(p,n) for n in p['nodes'] if n['id'] in (body.left_point_id,body.right_point_id)):
                    raise HTTPException(409,'Explicitly review every current source location before accepting a shared physical identity.')
                for stamp in stamps:
                    sheet=api.sheet_for(p,stamp['sheet_id'])
                    if not sheet.get('identity_verified') or sheet['line_id']!=state['line_id']:
                        raise HTTPException(409,'Confirm the printed sheet and full line identities before unifying physical points.')
                # A copy ensures that validation errors never leave a partly
                # rewired object for callers or future update operations.
                working=deepcopy(p)
                inherited={cid for previous in links if previous['status']=='ACCEPTED' and previous.get('point_id') in (body.left_point_id,body.right_point_id)
                           for cid in previous.get('source_candidate_ids',[])}
                try:keep=merge_identity(working,body.left_point_id,body.right_point_id,reviewer=actor['id'],reviewed_at=api.now())
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
