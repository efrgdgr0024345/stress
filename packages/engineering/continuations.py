"""Cross-sheet candidates and reviewed identity links; never paper measurements."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import re
from uuid import NAMESPACE_URL,uuid5

LIMIT=1000


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def uid(*parts):return str(uuid5(NAMESPACE_URL,':'.join(map(str,parts))))


def size_value(text):
    value=re.sub(r'\s*(?:NPS|INCHES|INCH|IN|["”])\s*',' ',text.upper()).strip()
    if not re.fullmatch(r'\d+(?:\.\d+|/\d+|[ -]+\d+/\d+)?',value):raise ValueError('An explicit nominal pipe size is required (for example 8 or 2 1/8).')
    result=sum((Fraction(v) for v in value.replace('-',' ').split()),Fraction())
    if not 0<result<=200:raise ValueError('Nominal pipe size is outside this supported profile.')
    return str(result)


def source_candidates(page,sheet):
    from packages.automation.recognize import text_rows
    result=[]
    # Restrict words spatially before forming rows: otherwise a material-table
    # row on the other side of the page can join the continuation label.
    for word in sorted(page['words'],key=lambda w:w['confidence'],reverse=True):
        if not re.fullmatch(r'CONT(?:INUED|INUATION)?[.]?(?:(?:ON|FROM|TO))?|MATCH(?:LINE)?',word['text'],re.I):continue
        x,y=word['bbox'][:2]
        local=[w for w in page['words'] if x-10<=w['bbox'][0]<=x+260 and y-3<=w['bbox'][1]<=y+40]
        rows=text_rows(local)
        row=next((r for r in rows if re.search(r'\bCONT(?:INUED|INUATION)?[.]?\s*(?:ON|FROM|TO)\b|\bMATCH\s*LINE\b',r['text'],re.I)),None)
        if not row:continue
        if any(abs(v['bbox'][0]-x)<8 and abs(v['bbox'][1]-y)<8 for v in result):continue
        nearby=[r for r in rows if 0<=r['y']-row['y']<=32]
        trigger=re.search(r'\bCONT|\bMATCH',row['text'],re.I)
        text=' '.join([row['text'][trigger.start():]]+[r['text'] for r in nearby if r is not row])[:1000]
        target=re.search(r'\bSHEET\s*(?:NO[.]?\s*)?(\d+)\b',text,re.I)
        reference=re.search(r'\b\d+["”]?\s*-\s*[A-Z0-9]+(?:-[A-Z0-9./]+){2,}',text,re.I)
        box=[min(r['bbox'][0] for r in nearby),min(r['bbox'][1] for r in nearby),max(r['bbox'][2] for r in nearby),max(r['bbox'][3] for r in nearby)]
        result.append({'id':uid(sheet['id'],'continuation-label',word['bbox']),
            'sheet_id':sheet['id'],'line_id':sheet['line_id'],'source_sha256':sheet['sha256'],
            'source_content_hash':sheet.get('content_hash'),'bbox':box,'source_text':text,
            'target_printed_sheet':int(target[1]) if target else None,
            'target_line_proposal':re.sub(r'["”\s]','',reference[0]).upper() if reference else None,
            'word_evidence_ids':[w['evidence_id'] for r in nearby for w in r['words'] if w.get('evidence_id')],
            'verification':'proposed'})
        if len(result)>=100:break
    return result


def candidate_matches(candidates,sheets):
    """Page index is never substituted for an unverified printed sheet identity."""
    by_id={s['id']:s for s in sheets};pairs=[]
    def printed(s):
        match=re.search(r'(?:\bSHEET\s*)?(\d+)\s*(?:OF|/)\s*\d+|^\s*(\d+)\s*$',s.get('printed_id',''),re.I)
        return int(next(v for v in match.groups() if v)) if match else None
    for i,left in enumerate(candidates[:LIMIT]):
        a=by_id.get(left['sheet_id'],{})
        for right in candidates[i+1:LIMIT]:
            b=by_id.get(right['sheet_id'],{})
            if a.get('id')==b.get('id') or left['line_id']!=right['line_id']:continue
            if not left.get('target_printed_sheet') or not right.get('target_printed_sheet'):continue
            if left['target_printed_sheet']!=printed(b) or right['target_printed_sheet']!=printed(a):continue
            if any(c.get('target_line_proposal') and c['target_line_proposal']!=other['line_id'].upper() for c,other in ((left,b),(right,a))):continue
            pairs.append({'id':uid('continuation-pair',left['id'],right['id']),'left_candidate_id':left['id'],
                'right_candidate_id':right['id'],'line_id':left['line_id'],'verification':'proposed',
                'status':'RECIPROCAL_REFERENCE_CANDIDATE' if a.get('identity_verified') and b.get('identity_verified') else 'SHEET_IDENTITY_REVIEW_REQUIRED'})
            if len(pairs)>=LIMIT:return pairs
    return pairs


def assess_pair(project,left_id,right_id,left_size,right_size,tolerance='0.01'):
    from packages.physical.constraints import solve
    nodes={n['id']:n for n in project['nodes']};a=nodes.get(left_id);b=nodes.get(right_id)
    if not a or not b or left_id==right_id:raise ValueError('Choose two distinct current physical points.')
    if a['line_id']!=b['line_id']:raise ValueError('Different full line IDs need a separately reviewed cross-line tie-in contract.')
    if {v['sheet_id'] for v in a['instances']} & {v['sheet_id'] for v in b['instances']}:
        raise ValueError('A continuation match requires separate source sheets; adjacent interfaces on one sheet remain distinct.')
    tolerance=Decimal(tolerance)
    if not tolerance.is_finite() or not 0<=tolerance<=Decimal('25.4'):raise ValueError('Continuation tolerance must be from 0 to 25.4 mm.')
    sizes=[size_value(left_size),size_value(right_size)]
    state={'left_point_id':left_id,'right_point_id':right_id,'line_id':a['line_id'],
           'left_size':left_size,'right_size':right_size,'tolerance_mm':str(tolerance),
           'delta_mm':{k:None for k in ('X','Y','Z')},'coordinates':{},'status':'REJECTED_SIZE_MISMATCH'}
    if sizes[0]!=sizes[1]:return state
    solution=solve(project);coords={c['point_id']:c['axes'] for c in solution['coordinates']}
    state['coordinate_input_sha256']=solution['input_sha256']
    state['coordinates']={key:{axis:coords.get(key,{}).get(axis,{}).get('value_mm') for axis in ('X','Y','Z')} for key in (left_id,right_id)}
    for axis in ('X','Y','Z'):
        x,y=(state['coordinates'][key][axis] for key in (left_id,right_id))
        if x is not None and y is not None:state['delta_mm'][axis]=str(Decimal(y)-Decimal(x))
    values=list(state['delta_mm'].values())
    if any(v is None for v in values):state['status']='COORDINATE_EVIDENCE_REQUIRED'
    elif any(abs(Decimal(v))>=Decimal('25.4') for v in values):state['status']='MATCH_TO_BE_CONFIRMED_BY_ENGINEER'
    elif any(abs(Decimal(v))>tolerance for v in values):state['status']='COORDINATE_DISCREPANCY'
    elif any(Decimal(v)!=0 for v in values):state['status']='WITHIN_TOLERANCE_REVIEW'
    else:state['status']='EXACT_COORDINATE_MATCH'
    return state


def source_stamp(project,node_ids):
    sheets={s['id']:s for s in project['sheets']}
    return [{'sheet_id':v['sheet_id'],'anchor':v['anchor'],'source_sha256':sheets[v['sheet_id']]['sha256'],
             'content_hash':sheets[v['sheet_id']].get('content_hash')}
            for n in project['nodes'] if n['id'] in node_ids for v in n['instances']]


def coordinate_proof(project,point_ids):
    from packages.physical.constraints import observations
    return digest(sorted((c for c in observations(project) if c.get('from_point_id') in point_ids or c.get('to_point_id') in point_ids),key=lambda c:c['id']))


def merge_identity(project,left_id,right_id):
    """Called only after reviewed exact-source/size/topology checks by the API.

    Never discard engineering records or opposite ends of a component.
    Source observations stay attached to their original sheet instances.
    """
    from packages.engineering import renumber
    from packages.physical import audit as physical_audit
    from packages.physical.constraints import solve
    established=set(project.get('point_aliases',{}).values())
    if right_id in established and left_id not in established:left_id,right_id=right_id,left_id
    nodes={n['id']:n for n in project['nodes']};keep,old=nodes[left_id],nodes[right_id]
    if keep['route']!=old['route']:raise ValueError('Confirm the common route identity before merging continuation depictions.')
    route=sorted((n for n in project['nodes'] if n['line_id']==keep['line_id'] and n['route']==keep['route']),key=lambda n:(n['order'],n['id']))
    if len({n['order'] for n in route})!=len(route):raise ValueError('Resolve ambiguous route order before merging identities.')
    positions={n['id']:i for i,n in enumerate(route)}
    if abs(positions[left_id]-positions[right_id])!=1:
        raise ValueError('Those depictions have other route points between them. A loop/revisit requires an explicit loop model; its topology cannot be collapsed.')
    if keep.get('station_mm') is not None and old.get('station_mm') is not None and Decimal(keep['station_mm'])!=Decimal(old['station_mm']):
        raise ValueError('Accepted route stations disagree. Resolve their source evidence before merging identities.')
    if {v['sheet_id'] for v in keep['instances']} & {v['sheet_id'] for v in old['instances']}:raise ValueError('Those point depictions share a sheet and cannot be silently merged.')
    kinds={keep['kind'],old['kind']}
    if len(kinds)>1 and not kinds<={'endpoint','continuation','flange','valve','instrument'}:
        raise ValueError('These component point kinds need an explicit common-interface classification first.')
    for component in physical_audit(project)['components']:
        used={v['point_id'] for v in component['ports'].values() if v}
        if {left_id,right_id}<=used:raise ValueError('Opposite interfaces of one component cannot be collapsed into a continuation.')
    keep['instances'].extend(deepcopy(old['instances']))
    keep['order']=min(keep['order'],old['order'])
    if keep.get('station_mm') is None and old.get('station_mm') is not None:
        for key in ('station_mm','dimension_input','evidence','verification'):
            if key in old:keep[key]=deepcopy(old[key])
    if keep['kind'] in ('endpoint','continuation') and old['kind'] not in ('endpoint','continuation'):keep['kind']=old['kind']
    if keep['kind']=='endpoint':keep['kind']='continuation'
    refs=[]
    for node in (keep,old):
        refs.extend(deepcopy(node.get('source_feature_links',[])))
        if node.get('source_feature_id'):refs.append({'id':node['source_feature_id'],'role':node['source_feature_role']})
    if refs:keep['source_feature_links']=list({(v['id'],v['role']):v for v in refs}.values())
    project['nodes']=[n for n in project['nodes'] if n['id']!=right_id]
    for node in project['nodes']:
        if node.get('takeoff_id')==right_id:node['takeoff_id']=left_id
    for c in project.get('physical_model',{}).get('components',[]):
        for port in c['ports'].values():
            if port and port['point_id']==right_id:port['point_id']=left_id
    for constraint in project.get('physical_model',{}).get('constraints',[]):
        for key in ('from_point_id','to_point_id'):
            if constraint.get(key)==right_id:constraint[key]=left_id
    model=project.get('analysis_model',{})
    if model.get('origin_point_id')==right_id:model['origin_point_id']=left_id
    elements={}
    for element in model.get('elements',[]):
        original=deepcopy(element)
        for key in ('from_point_id','to_point_id'):
            if element.get(key)==right_id:element[key]=left_id
        for c in element.get('geometry_source_inputs',[]):
            for key in ('from_point_id','to_point_id'):
                if c.get(key)==right_id:c[key]=left_id
        a,b=element['from_point_id'],element['to_point_id']
        if a==b:
            if any(element.get(k) is not None and Decimal(element[k])!=0 for k in ('dx_mm','dy_mm','dz_mm')):
                raise ValueError('An entered nonzero analysis element would collapse. Reconcile that engineering input first.')
            model.setdefault('retired_elements',[]).append({'reason':'Shared continuation identity; no remaining physical span','element':original})
            continue
        element['id']=uid(project['id'],a,b)
        if element['id'] in elements:raise ValueError('Merging would conflate two analysis records. Reconcile their source properties first.')
        elements[element['id']]=element
    if 'elements' in model:model['elements']=list(elements.values())
    aliases=project.setdefault('point_aliases',{})
    for retired,current in list(aliases.items()):
        if current==right_id:aliases[retired]=left_id
    aliases[right_id]=left_id
    project.setdefault('retired_points',[]).append({'reason':'Reviewed shared continuation identity','point':deepcopy(old),'canonical_point_id':left_id})
    for link in project.get('continuations',[]):
        pair={aliases.get(v,v) for v in (link.get('left_point_id'),link.get('right_point_id'))}
        if (link['status']=='ACCEPTED' and link.get('point_id') in (left_id,right_id)) or len(pair)==1:
            link['status']='SUPERSEDED'
    if any(i['code']=='COORDINATE_MISMATCH' for i in solve(project)['issues']):raise ValueError('Merging introduces conflicting coordinate constraints; source values were not accepted.')
    project['numbering_map']=renumber(project['nodes'])
    return keep


def audit(project):
    nodes={n['id']:n for n in project['nodes']};sheets={s['id']:s for s in project['sheets']};issues=[];solution=None
    for link in project.get('continuations',[]):
        if link['status'] in ('REJECTED','SUPERSEDED'):continue
        points=[link['point_id']] if link.get('point_id') else [project.get('point_aliases',{}).get(v,v) for v in (link['left_point_id'],link['right_point_id'])]
        stale=False
        for stamp in link['source_stamps']:
            sheet=sheets.get(stamp['sheet_id'])
            current=sheet and (sheet.get('content_hash')==stamp['content_hash'] if stamp['content_hash'] else sheet['sha256']==stamp['source_sha256'])
            depicted=any(n in nodes and any(v['sheet_id']==stamp['sheet_id'] and v['anchor']==stamp['anchor'] for v in nodes[n]['instances']) for n in points)
            if not current or not depicted:stale=True
        if stale or any(n not in nodes for n in points):code='CONTINUATION_SOURCE_STALE'
        elif link['status']!='ACCEPTED':code=link['status']
        else:
            # Accepted identity is source- and dimension-bound; subsequent edits
            # cannot preserve an approval over conflicting independent coordinates.
            from packages.physical.constraints import solve
            solution=solution or solve(project)
            if any(i['code']=='COORDINATE_MISMATCH' and set(points)&set(i.get('point_ids',[])) for i in solution['issues']):code='CONTINUATION_COORDINATE_CONFLICT'
            elif coordinate_proof(project,set(points))!=link.get('coordinate_proof_sha256'):code='CONTINUATION_COORDINATES_CHANGED'
            else:continue
        issues.append({'code':code,'continuation_id':link['id'],'line_id':link['line_id'],
                       'point_ids':points,'severity':'critical','message':'Continuation '+code.replace('_',' ').lower()+'. Original source coordinates are retained.'})
    bad_links={i['continuation_id'] for i in issues}
    resolved={cid for link in project.get('continuations',[]) if link['status']=='ACCEPTED' and link['id'] not in bad_links
              for cid in link.get('source_candidate_ids',[])}
    for candidate in project.get('automation',{}).get('continuation_candidates',[]):
        if candidate['id'] not in resolved:
            issues.append({'code':'UNRESOLVED_CONTINUATION_REFERENCE','continuation_id':'source:'+candidate['id'],
                'line_id':candidate['line_id'],'point_ids':[],'sheet_id':candidate['sheet_id'],'bbox':candidate['bbox'],
                'evidence_id':candidate['id'],'severity':'critical',
                'message':'Printed continuation reference needs a proved matching interface or an explicit engineering boundary decision; no connection was invented.'})
    return issues


def apply_reasons(project):
    issues=audit(project)
    for node in project['nodes']:
        reasons=sorted({i['code'] for i in issues if node['id'] in i['point_ids']})
        if reasons:node['continuation_review_reasons']=reasons
        else:node.pop('continuation_review_reasons',None)
    return issues
