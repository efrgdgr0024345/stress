"""Printed coordinate transcriptions are proposals until explicitly accepted."""
from decimal import Decimal,InvalidOperation
import hashlib
import json
from packages.engineering import source_location_reviewed,source_observations
from packages.engineering.coordinates import coordinate_value
from packages.physical import identity


def inspection_fingerprint(project,point_id,sheet_id):
    point=next((n for n in project['nodes'] if n['id']==point_id),None)
    sheet=next((s for s in project['sheets'] if s['id']==sheet_id),None)
    if not point or not sheet or not source_location_reviewed(point,{sheet_id:sheet},sheet_id):return None
    observation=next((o for o in source_observations(point) if o.get('sheet_id')==sheet_id),None)
    instance=next((i for i in point['instances'] if i['sheet_id']==sheet_id),None)
    if not observation or not instance:return None
    value={'point_id':point_id,'kind':point['kind'],'line_id':point['line_id'],'sheet_id':sheet_id,
        'content_hash':sheet.get('content_hash'),'source_sha256':sheet['sha256'] if not sheet.get('content_hash') else None,
        'anchor':instance['anchor'],'observation_id':observation.get('id')}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def candidate_point(project,candidate):
    uid=candidate.get('point_id');aliases=project.get('point_aliases',{});seen=set()
    while uid in aliases:
        if uid in seen:return None
        seen.add(uid);uid=aliases[uid]
    return uid


def source_coordinate_current(project,constraint):
    candidate=next((c for c in project.get('automation',{}).get('continuation_candidates',[]) if c['id']==constraint.get('source_candidate_id')),None)
    if not candidate or candidate_point(project,candidate)!=constraint['from_point_id'] or candidate['sheet_id']!=constraint['sheet_id']:return False
    text=candidate.get('printed_coordinate_proposals',{}).get(constraint['axis'])
    if text!=constraint.get('source_text') or candidate.get('source_format','STANDARD')!=constraint.get('source_format','STANDARD'):return False
    try:
        if Decimal(coordinate_value(text,constraint['axis'],candidate.get('source_format','STANDARD'))['value_mm'])!=Decimal(constraint['value_mm']):return False
    except (ValueError,TypeError,InvalidOperation):return False
    fingerprint=inspection_fingerprint(project,constraint['from_point_id'],constraint['sheet_id'])
    return bool(fingerprint and fingerprint==constraint.get('source_inspection_sha256'))


def proposals(project):
    sheets={s['id']:s for s in project['sheets']};points={n['id']:n for n in project['nodes']}
    constraints={c['id']:c for c in project.get('physical_model',{}).get('constraints',[])}
    result=[]
    for candidate in project.get('automation',{}).get('continuation_candidates',[]):
        for axis,text in candidate.get('printed_coordinate_proposals',{}).items():
            point_id=candidate_point(project,candidate);point=points.get(point_id);sheet=sheets.get(candidate['sheet_id'])
            uid=identity(project['id'],'printed-source-coordinate',candidate['id'],axis)
            current=bool(sheet and (candidate.get('source_content_hash')==sheet.get('content_hash') if candidate.get('source_content_hash') else candidate['source_sha256']==sheet['sha256']))
            status='PROPOSED';parsed=None
            try:parsed=coordinate_value(text,axis,candidate.get('source_format','STANDARD'))
            except ValueError:status='SOURCE_SYNTAX_REVIEW_REQUIRED'
            if not current:status='SOURCE_CHANGED'
            elif not point:status='SOURCE_POINT_REQUIRED'
            elif not inspection_fingerprint(project,point_id,sheet['id']):status='SOURCE_INSPECTION_REQUIRED'
            old=constraints.get(uid)
            if old:
                status='ACCEPTED' if old.get('verification')=='reviewed' and source_coordinate_current(project,old) else 'ACCEPTED_SOURCE_STALE'
            result.append({'id':uid,'candidate_id':candidate['id'],'source_label':candidate.get('source_label'),
                'point_id':point_id,'review_label':point.get('review_label') if point else None,'sheet_id':candidate['sheet_id'],
                'axis':axis,'source_text':text,'source_format':candidate.get('source_format','STANDARD'),
                'proposed_value_mm':parsed['value_mm'] if parsed else None,'accepted_value_mm':old['value_mm'] if old and status=='ACCEPTED' else None,
                'status':status,'source_sha256':candidate['source_sha256'],'source_content_hash':candidate.get('source_content_hash'),
                'source_bbox':candidate.get('coordinate_text_bbox'),'source_evidence':candidate.get('source_evidence'),
                'source_current':current,'can_accept':bool(current and parsed and point and inspection_fingerprint(project,point_id,sheet['id'])),
                'engineering_approved':False})
    return result
