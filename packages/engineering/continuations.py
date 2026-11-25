"""Cross-sheet candidates and reviewed identity links; never paper measurements."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import re
from uuid import NAMESPACE_URL,uuid5

LIMIT=1000
SOURCE_REVIEW_LIMIT=2000
SOURCE_REASONS=('MISSING_PEER_IN_PACK','EQUIPMENT_BOUNDARY','ACCEPTED_XYZ_REQUIRED',
                'SOURCE_INTERFACE_UNCONFIRMED','LINE_OR_SIZE_MISMATCH')


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


def independent_source_coordinates(project,node,inputs=None):
    """Direct accepted XYZ on every depicting sheet; deltas never prove both ends."""
    from packages.physical.constraints import observations
    inputs=inputs if inputs is not None else observations(project)
    sheets={s['id']:s for s in project['sheets']};values={};missing=[];conflicts=[]
    for axis in ('X','Y','Z'):
        observed=[]
        for sheet_id in {i['sheet_id'] for i in node['instances']}:
            sheet=sheets.get(sheet_id);direct=[]
            for c in inputs:
                if (c.get('kind')!='COORDINATE' or c.get('cod_derivation') or c.get('axis')!=axis or
                    c.get('from_point_id')!=node['id'] or c.get('sheet_id')!=sheet_id or not c.get('evidence','').strip()):continue
                current=bool(sheet and (c.get('source_content_hash')==sheet.get('content_hash')
                    if c.get('source_content_hash') else c.get('source_sha256')==sheet.get('sha256')))
                if current:direct.append(Decimal(c['value_mm']))
            if not direct:missing.append({'sheet_id':sheet_id,'axis':axis})
            observed.extend(direct)
        if observed and any(v!=observed[0] for v in observed):conflicts.append(axis)
        values[axis]=str(observed[0]) if observed and axis not in conflicts and not any(m['axis']==axis for m in missing) else None
    return {'coordinates':values,'missing':missing,'conflicting_axes':conflicts}


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
    direct={n['id']:independent_source_coordinates(project,n,solution['inputs']) for n in (a,b)}
    state['independent_source_coordinates']=deepcopy(direct)
    state['coordinates']={key:{axis:direct[key]['coordinates'][axis]
        if coords.get(key,{}).get(axis,{}).get('value_mm') is not None else None for axis in ('X','Y','Z')} for key in (left_id,right_id)}
    for axis in ('X','Y','Z'):
        x,y=(state['coordinates'][key][axis] for key in (left_id,right_id))
        if x is not None and y is not None:state['delta_mm'][axis]=str(Decimal(y)-Decimal(x))
    values=list(state['delta_mm'].values())
    if any(v['conflicting_axes'] for v in direct.values()):state['status']='COORDINATE_EVIDENCE_CONFLICT'
    elif any(v is None for v in values):state['status']='COORDINATE_EVIDENCE_REQUIRED'
    elif any(abs(Decimal(v))>=Decimal('25.4') for v in values):state['status']='MATCH_TO_BE_CONFIRMED_BY_ENGINEER'
    elif any(abs(Decimal(v))>tolerance for v in values):state['status']='COORDINATE_DISCREPANCY'
    elif any(Decimal(v)!=0 for v in values):state['status']='WITHIN_TOLERANCE_REVIEW'
    else:state['status']='EXACT_COORDINATE_MATCH'
    return state


def source_stamp(project,node_ids):
    sheets={s['id']:s for s in project['sheets']}
    return [{'sheet_id':v['sheet_id'],'anchor':v['anchor'],'source_sha256':sheets[v['sheet_id']]['sha256'],
             'content_hash':sheets[v['sheet_id']].get('content_hash'),
             **{k:sheets[v['sheet_id']].get(k) for k in ('printed_id','line_id','identity_verified')}}
            for n in project['nodes'] if n['id'] in node_ids for v in n['instances']]


def coordinate_proof(project,point_ids):
    from packages.physical.constraints import observations
    return digest(sorted((c for c in observations(project) if c.get('from_point_id') in point_ids or c.get('to_point_id') in point_ids),key=lambda c:c['id']))


def candidate_point_id(project,candidate):
    point=candidate.get('point_id') or project.get('source_review',{}).get('observation_points',{}).get(
        candidate.get('source_observation_id') or candidate['id'])
    aliases=project.get('point_aliases',{});seen=set()
    while point in aliases and point not in seen:seen.add(point);point=aliases[point]
    return point


def source_binding(project,candidate,solution=None):
    """Bind a disposition to physical evidence; display numbers/bubbles are not proof."""
    from packages.engineering import topology
    from packages.physical.constraints import solve
    sheet=next((s for s in project['sheets'] if s['id']==candidate['sheet_id']),None)
    point_id=candidate_point_id(project,candidate)
    point=next((n for n in project['nodes'] if n['id']==point_id),None)
    instance=next((i for i in point['instances'] if i['sheet_id']==candidate['sheet_id']),None) if point else None
    current=bool(sheet and (candidate.get('source_content_hash')==sheet.get('content_hash')
        if candidate.get('source_content_hash') else candidate.get('source_sha256')==sheet.get('sha256')))
    box=candidate.get('bbox',[])
    if not sheet or len(box)!=4 or not 0<=box[0]<box[2]<=sheet['width'] or not 0<=box[1]<box[3]<=sheet['height']:current=False
    binding={'candidate':{k:deepcopy(candidate.get(k)) for k in (
        'id','sheet_id','line_id','source_sha256','source_content_hash','source_text','bbox','anchor',
        'source_label','target_printed_sheet','target_line_proposal','source_observation_id','target_kind',
        'printed_coordinate_proposals','source_format','coordinate_text_bbox','nominal_size_proposal',
        'source_evidence','interface_status')},
        'sheet':{k:deepcopy(sheet.get(k)) for k in ('id','sha256','content_hash','printed_id','line_id','identity_verified')} if sheet else None,
        'project_line_id':project.get('line_id'),'point_id':point_id,'point':None,'source_current':current}
    if point:
        solution=solution or solve(project)
        axes=next((v['axes'] for v in solution['coordinates'] if v['point_id']==point_id),{})
        constraints={cid for axis in axes.values() for cid in solution['evidence_groups'].get(axis.get('evidence_group'),{}).get('constraint_ids',[])}
        relevant_inputs=[v for v in solution['inputs'] if v['id'] in constraints]
        raw_inputs=[v for v in project.get('physical_model',{}).get('constraints',[])
                    if v.get('from_point_id')==point_id or v.get('to_point_id')==point_id]
        interfaces=[{'id':c['id'],'kind':c['kind'],'verification':c.get('verification'),'ports':c['ports']}
                    for c in project.get('physical_model',{}).get('components',[])
                    if any(p and p.get('point_id')==point_id for p in c.get('ports',{}).values())]
        source_proofs=_source_observations(point)
        for source in source_proofs:source.pop('review_history',None)
        binding['point']={k:deepcopy(point.get(k)) for k in (
            'id','kind','line_id','route','order','takeoff_id','topology_state','station_mm','dimension_input','verification')}
        binding['point'].update(anchor=deepcopy(instance['anchor']) if instance else None,
            evidence_sha256=digest(point.get('evidence','')),source_review_sha256=digest(source_proofs),
            source_exception_sha256=digest([v for v in point.get('source_review_reasons',[]) if v!='UNRESOLVED_CONTINUATION_REFERENCE']),
            coordinate_values={axis:{k:value.get(k) for k in ('value_mm','relative_mm','status','tolerance_mm')}
                               for axis,value in axes.items()},
            coordinate_evidence_sha256=digest({'accepted':relevant_inputs,'source':raw_inputs,'stored':point.get('coordinates_mm')}),
            topology_evidence_sha256=digest([e for e in topology(project['nodes'])['edges'] if point_id in (e['from'],e['to'])]),
            interface_evidence_sha256=digest(interfaces))
    return binding


def make_source_review(project,candidate,decision,reason_code,evidence,reviewed_by=None,reviewed_at=None):
    if reason_code not in SOURCE_REASONS:raise ValueError('Choose a supported continuation endpoint reason.')
    if len(evidence.strip())<10:raise ValueError('Describe the actual source evidence for this endpoint disposition.')
    binding=source_binding(project,candidate)
    if decision!='REOPEN' and not binding['source_current']:raise ValueError('Continuation source evidence changed or is unavailable; refresh it before deciding.')
    status={'ENDPOINT_EXCEPTION':'ENDPOINT_EXCEPTION','REJECT_MATCH':'REJECTED_MATCH',
            'DECLARE_EXTERNAL_BOUNDARY':'EXTERNAL_BOUNDARY','REOPEN':'REOPENED'}.get(decision)
    if status is None:raise ValueError('Unsupported source-reference decision.')
    return {'id':uid(project['id'],candidate['id'],len(project.get('continuation_source_reviews',[])),decision,binding,reason_code,evidence,reviewed_by,reviewed_at),
        'candidate_id':candidate['id'],'point_id':candidate_point_id(project,candidate),
        'sheet_id':candidate['sheet_id'],'line_id':candidate['line_id'],'source_label':candidate.get('source_label'),
        'decision':decision,'status':status,'reason_code':reason_code,'evidence':evidence.strip(),
        'verification':'reviewed' if reviewed_by else 'proposed','engineering_approved':False,
        'binding':binding,'binding_sha256':digest(binding),
        **({'reviewed_by':reviewed_by,'reviewed_at':reviewed_at} if reviewed_by else {})}


def create_source_exception(project,candidate,reason_code,evidence):
    """Idempotent machine proposal; never overwrite a reviewed or reopened record."""
    records=project.setdefault('continuation_source_reviews',[])
    previous=next((v for v in reversed(records) if v['candidate_id']==candidate['id']),None)
    if previous:return previous
    if len(records)>=SOURCE_REVIEW_LIMIT:raise ValueError('Continuation source review allowance reached.')
    record=make_source_review(project,candidate,'ENDPOINT_EXCEPTION',reason_code,evidence)
    records.append(record)
    return record


def source_review_records(project):
    candidates={c['id']:c for c in project.get('automation',{}).get('continuation_candidates',[])}
    records=project.get('continuation_source_reviews',[])
    latest={r['candidate_id']:r['id'] for r in records}
    contexts={};result=[];solution=None
    if records:
        from packages.physical.constraints import solve
        solution=solve(project)
    for record in records:
        candidate=candidates.get(record['candidate_id'])
        if candidate and candidate['id'] not in contexts:contexts[candidate['id']]=source_binding(project,candidate,solution)
        binding=contexts.get(record['candidate_id'])
        stale=not binding or not binding['source_current'] or digest(binding)!=record.get('binding_sha256')
        is_latest=latest[record['candidate_id']]==record['id']
        result.append({**deepcopy(record),'is_latest':is_latest,'current':is_latest and not stale,
            'stale':bool(stale),'effective_status':'STALE' if stale else record['status']})
    return result


def source_review_states(project):
    """Current per-reference display state, distinct from accepted peer identity."""
    records={r['candidate_id']:r for r in source_review_records(project) if r['is_latest']}
    bad={i['continuation_id'] for i in identity_audit(project)}
    shared={cid:link for link in project.get('continuations',[]) if link['status']=='ACCEPTED' and link['id'] not in bad
            for cid in link.get('source_candidate_ids',[])}
    points={n['id']:n for n in project['nodes']};states={}
    for candidate in project.get('automation',{}).get('continuation_candidates',[]):
        record=records.get(candidate['id']);link=shared.get(candidate['id'])
        point_id=candidate_point_id(project,candidate) or (link.get('point_id') if link else None);point=points.get(point_id)
        status='SHARED_IDENTITY_REVIEWED' if candidate['id'] in shared else record['effective_status'] if record else 'UNRESOLVED'
        states[candidate['id']]={'candidate_id':candidate['id'],'point_id':point_id,
            'point_label':str(point['number']) if point and point.get('number') is not None else point.get('review_label') if point else None,
            'source_label':candidate.get('source_label'),'status':status,'effective_status':status,
            'reason_code':None if link else record.get('reason_code') if record else None,
            'evidence':link.get('evidence') if link else record.get('evidence') if record else None,
            'verification':'reviewed' if candidate['id'] in shared else record.get('verification') if record else 'proposed',
            'current':bool(candidate['id'] in shared or record and record['current']),
            'stale':bool(candidate['id'] not in shared and record and record['stale']),
            'review_id':link['id'] if link else record['id'] if record else None,'engineering_approved':False}
    return states


def _source_observations(node):
    from packages.engineering import source_observations
    return deepcopy(source_observations(node))


def merge_identity(project,left_id,right_id,reviewer=None,reviewed_at=None):
    """Called only after reviewed exact-source/size/topology checks by the API.

    Never discard engineering records or opposite ends of a component.
    Source observations stay attached to their original sheet instances.
    """
    from packages.engineering import renumber,topology_assigned
    from packages.physical import audit as physical_audit
    from packages.physical.constraints import solve
    nodes={n['id']:n for n in project['nodes']}
    if left_id not in nodes or right_id not in nodes or left_id==right_id:raise ValueError('Choose two distinct current physical points.')
    established=set(project.get('point_aliases',{}).values())
    left_assigned,right_assigned=topology_assigned(nodes[left_id]),topology_assigned(nodes[right_id])
    if (right_assigned and not left_assigned) or (left_assigned==right_assigned and right_id in established and left_id not in established):
        left_id,right_id=right_id,left_id
    keep,old=nodes[left_id],nodes[right_id]
    assigned=topology_assigned(keep);both_assigned=assigned and topology_assigned(old)
    if keep['line_id']!=old['line_id']:raise ValueError('Different full line identities cannot be silently unified.')
    for node in (keep,old):
        if not topology_assigned(node) and any(node.get(k) is not None for k in ('route','order','takeoff_id')):
            raise ValueError('An unassigned source point carries conflicting route metadata. Reconcile it before merging.')
    if both_assigned:
        if keep['route']!=old['route']:raise ValueError('Confirm the common route identity before merging continuation depictions.')
        route=sorted((n for n in project['nodes'] if topology_assigned(n) and n['line_id']==keep['line_id'] and n['route']==keep['route']),key=lambda n:(n['order'],n['id']))
        if len({n['order'] for n in route})!=len(route):raise ValueError('Resolve ambiguous route order before merging identities.')
        positions={n['id']:i for i,n in enumerate(route)}
        if abs(positions[left_id]-positions[right_id])!=1:
            raise ValueError('Those depictions have other route points between them. A loop/revisit requires an explicit loop model; its topology cannot be collapsed.')
    if keep.get('station_mm') is not None and old.get('station_mm') is not None and Decimal(keep['station_mm'])!=Decimal(old['station_mm']):
        raise ValueError('Accepted route stations disagree. Resolve their source evidence before merging identities.')
    if keep.get('station_mm') is not None and old.get('station_mm') is not None:
        from packages.physical.stations import apply_station_reasons,station_comparison_basis
        checked=deepcopy(project)
        apply_station_reasons(checked)
        checked_nodes={n['id']:n for n in checked['nodes']}
        first_basis=station_comparison_basis(checked_nodes[keep['id']])
        second_basis=station_comparison_basis(checked_nodes[old['id']])
        if not first_basis or first_basis!=second_basis:
            raise ValueError('Accepted station datums are different or stale. Review their source basis before merging identities.')
    if {v['sheet_id'] for v in keep['instances']} & {v['sheet_id'] for v in old['instances']}:raise ValueError('Those point depictions share a sheet and cannot be silently merged.')
    kinds={keep['kind'],old['kind']}
    if len(kinds)>1 and not kinds<={'endpoint','continuation','flange','valve','instrument'}:
        raise ValueError('These component point kinds need an explicit common-interface classification first.')
    for component in physical_audit(project)['components']:
        used={v['point_id'] for v in component['ports'].values() if v}
        if {left_id,right_id}<=used:raise ValueError('Opposite interfaces of one component cannot be collapsed into a continuation.')
    keep['instances'].extend(deepcopy(old['instances']))
    if both_assigned:keep['order']=min(keep['order'],old['order'])
    elif not assigned:keep.update(route=None,order=None,number=None,takeoff_id=None,topology_state='UNASSIGNED')
    source_observations=_source_observations(keep)+_source_observations(old)
    if source_observations:keep['source_observations']=list({digest(v):v for v in source_observations}.values())
    if not keep.get('source_observation') and old.get('source_observation'):keep['source_observation']=deepcopy(old['source_observation'])
    keep['source_review_reasons']=sorted(set(keep.get('source_review_reasons',[]))|set(old.get('source_review_reasons',[])))
    if keep.get('station_mm') is None and old.get('station_mm') is not None:
        if keep.get('station_proof'):
            keep.setdefault('station_proof_history',[]).append(deepcopy(keep['station_proof']))
        for key in ('station_mm','dimension_input','evidence','verification'):
            if key in old:keep[key]=deepcopy(old[key])
        for key in ('station_proof','manual_station_basis'):
            if key in old:keep[key]=deepcopy(old[key])
            else:keep.pop(key,None)
        for key in ('station_proof_history','station_history'):
            if old.get(key):keep.setdefault(key,[]).extend(deepcopy(old[key]))
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
    for constraint in project.get('physical_model',{}).get('constraints',[])+project.get('physical_model',{}).get('station_constraints',[]):
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
    from packages.engineering.graph_review import renumber_project
    renumber_project(project,'Unified reviewed continuation identity and retained every physical numbering alias',reviewer,reviewed_at)
    # Renumbering atomically replaces the project with its validated copy.
    # Return that current canonical object, not the detached pre-renumber node.
    return next(n for n in project['nodes'] if n['id']==left_id)


def identity_audit(project):
    nodes={n['id']:n for n in project['nodes']};sheets={s['id']:s for s in project['sheets']};issues=[];solution=None
    for link in project.get('continuations',[]):
        if link['status'] in ('REJECTED','SUPERSEDED'):continue
        points=[link['point_id']] if link.get('point_id') else [project.get('point_aliases',{}).get(v,v) for v in (link['left_point_id'],link['right_point_id'])]
        stale=False
        for stamp in link['source_stamps']:
            sheet=sheets.get(stamp['sheet_id'])
            current=sheet and (sheet.get('content_hash')==stamp['content_hash'] if stamp['content_hash'] else sheet['sha256']==stamp['source_sha256'])
            current=current and all(sheet.get(k)==stamp.get(k) for k in ('printed_id','line_id','identity_verified'))
            depicted=any(n in nodes and any(v['sheet_id']==stamp['sheet_id'] and v['anchor']==stamp['anchor'] for v in nodes[n]['instances']) for n in points)
            if not current or not depicted:stale=True
        if stale or any(n not in nodes or nodes[n]['line_id']!=link['line_id'] for n in points):code='CONTINUATION_SOURCE_STALE'
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
    return issues


def audit(project):
    issues=identity_audit(project)
    states=source_review_states(project)
    for candidate in project.get('automation',{}).get('continuation_candidates',[]):
        state=states[candidate['id']]
        point_ids=[state['point_id']] if any(n['id']==state['point_id'] for n in project['nodes']) else []
        base={'continuation_id':'source:'+candidate['id'],'line_id':candidate['line_id'],
            'point_ids':point_ids,'sheet_id':candidate['sheet_id'],'bbox':candidate['bbox'],
            'evidence_id':candidate['id'],'reason_code':state['reason_code'],'evidence':state['evidence']}
        if state['status']=='SHARED_IDENTITY_REVIEWED':continue
        if state['status'] in ('ENDPOINT_EXCEPTION','REJECTED_MATCH'):
            issues.append({**base,'code':'CONTINUATION_ENDPOINT_EXCEPTION','severity':'critical',
                'verification':state['verification'],'message':'Continuation endpoint exception: '+state['reason_code']+'. '+state['evidence']+' No peer identity or connection was accepted.'})
            continue
        if state['status']=='EXTERNAL_BOUNDARY':
            issues.append({**base,'code':'CONTINUATION_EXTERNAL_BOUNDARY','severity':'review',
                'verification':state['verification'],'message':'Reviewed external project boundary: '+state['evidence']+' No peer identity or connection was created.'})
            continue
        if state['status']=='STALE':
            issues.append({**base,'code':'CONTINUATION_SOURCE_DECISION_STALE','severity':'critical',
                'message':'Continuation source disposition refers to changed source, point, coordinate or topology evidence; review it again.'})
        if state['status'] in ('UNRESOLVED','REOPENED','STALE'):
            issues.append({'code':'UNRESOLVED_CONTINUATION_REFERENCE','continuation_id':'source:'+candidate['id'],
                'line_id':candidate['line_id'],'point_ids':point_ids,'sheet_id':candidate['sheet_id'],'bbox':candidate['bbox'],
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
