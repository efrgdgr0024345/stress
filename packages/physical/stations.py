"""Accepted along-centreline station constraints; page/XYZ lengths are never inputs."""
from collections import deque
from copy import deepcopy
from decimal import Decimal,localcontext
import hashlib
import json

MAX_POINTS=2000
MAX_CONSTRAINTS=6000
SCHEMA='along-route-stations-1'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def station_constraints(project):
    return project.get('physical_model',{}).get('station_constraints',[])


def canonical_point_id(project,point):
    aliases=project.get('point_aliases',{});seen=set()
    while point in aliases and point not in seen:seen.add(point);point=aliases[point]
    return point


def source_stamps(project,point_ids):
    sheets={s['id']:s for s in project.get('sheets',[])};result=[]
    for node in project['nodes']:
        if node['id'] not in point_ids:continue
        for instance in node.get('instances',[]):
            sheet=sheets.get(instance['sheet_id'])
            if sheet:result.append({'point_id':node['id'],'sheet_id':sheet['id'],'line_id':node['line_id'],
                'source_sha256':sheet.get('sha256'),'content_hash':deepcopy(sheet.get('content_hash')),
                'anchor':deepcopy(instance['anchor'])})
    return result


def basis_id(kind,line,route,origin=None):
    return kind+':'+digest([line,route,origin])[:24]


def _manual_anchor(project,node):
    proof=node.get('station_proof')
    if proof:return deepcopy(proof.get('retained_manual_anchor'))
    if node.get('station_mm') is None or not node.get('evidence','').strip() or node.get('verification')=='proposed':return None
    frame=node.get('manual_station_basis') or {'basis':'ABSOLUTE','basis_id':basis_id('ABSOLUTE',node['line_id'],node.get('route')),
        'basis_point_id':None,'line_id':node['line_id'],'route':node.get('route')}
    sheet_id=next((i['sheet_id'] for i in node.get('instances',[])),None)
    sheet=next((s for s in project.get('sheets',[]) if s['id']==sheet_id),{})
    return {'id':'manual-station:'+node['id'],'kind':'MANUAL_RELATIVE' if frame['basis']=='LOCAL_ORIGIN' else 'ABSOLUTE',
        'from_point_id':node['id'],'to_point_id':None,'value_mm':node['station_mm'],'tolerance_mm':'0',
        'source_text':node.get('dimension_input') or node['station_mm']+' mm','source_format':'STANDARD',
        'distance_basis':'ALONG_CENTRELINE','evidence':node['evidence'],'verification':'reviewed',
        'sheet_id':sheet_id,'source_sha256':sheet.get('sha256'),'source_content_hash':deepcopy(sheet.get('content_hash')),
        'source_point_stamps':source_stamps(project,{node['id']}),'source':'manual-node','manual_basis':deepcopy(frame)}


def _source_current(project,constraint,nodes,sheets):
    sheet=sheets.get(constraint.get('sheet_id'))
    if not sheet:return False
    if constraint.get('source_content_hash'):
        if constraint['source_content_hash']!=sheet.get('content_hash'):return False
    elif constraint.get('source_sha256')!=sheet.get('sha256'):return False
    stamps=constraint.get('source_point_stamps')
    if not stamps:return False
    for stamp in stamps:
        node=nodes.get(canonical_point_id(project,stamp.get('point_id')))
        source=sheets.get(stamp.get('sheet_id'))
        if not node or not source or node['line_id']!=stamp.get('line_id'):return False
        current=(stamp.get('content_hash')==source.get('content_hash') if stamp.get('content_hash') else stamp.get('source_sha256')==source.get('sha256'))
        if not current or not any(i['sheet_id']==source['id'] and list(i['anchor'])==list(stamp.get('anchor',[])) for i in node['instances']):return False
    return True


def _point_context(project,node):
    sheets={s['id']:s for s in project.get('sheets',[])}
    return {**{k:deepcopy(node.get(k)) for k in ('id','line_id','route','order','topology_state','kind')},
        'topology_state':node.get('topology_state','ASSIGNED'),
        'sources':[{'sheet_id':i['sheet_id'],'anchor':deepcopy(i['anchor']),
            'content_hash':deepcopy(sheets.get(i['sheet_id'],{}).get('content_hash')),
            'source_sha256':sheets.get(i['sheet_id'],{}).get('sha256')} for i in node.get('instances',[])]}


def _issue(code,message,points=None,constraint=None,**details):
    return {'code':code,'message':message,'point_ids':sorted(set(points or [])),
        **({'constraint_id':constraint} if constraint else {}),'severity':'critical',**details}


def solve_stations(project):
    from packages.engineering import topology_assigned
    nodes={n['id']:n for n in project['nodes']};sheets={s['id']:s for s in project.get('sheets',[])}
    raw=deepcopy(station_constraints(project));manual=[c for n in nodes.values() if (c:=_manual_anchor(project,n))]
    entries=raw+manual;issues=[];valid=[];blocked=[];evaluation={}
    global_sha=digest({'constraints':raw,'manual':manual,'points':[_point_context(project,n) for n in nodes.values()]})
    if len(nodes)>MAX_POINTS or len(entries)>MAX_CONSTRAINTS:
        return {'schema':SCHEMA,'distance_basis':'ALONG_CENTRELINE','points':[],'inputs':[],'input_sha256':global_sha,
            'can_apply':False,'physical_stations_modified':False,'drawing_pixels_used':False,'xyz_distance_used':False,
            'issues':[_issue('STATION_SOLVER_LIMIT','Station constraints exceed the bounded 2,000-point / 6,000-input solver. No partial result is qualified.')]}
    for original in entries:
        c=deepcopy(original);a=canonical_point_id(project,c.get('from_point_id'));b=canonical_point_id(project,c.get('to_point_id')) if c.get('to_point_id') else None
        c.update(from_point_id=a,to_point_id=b);points=[p for p in (a,b) if p in nodes]
        evaluation[c['id']]={'constraint':original,'active':False}
        if c.get('verification')!='reviewed':
            issues.append(_issue('STATION_SOURCE_REVIEW_REQUIRED','Station source text is a proposal and has not been accepted.',points,c['id']));continue
        code=None;message=''
        if a not in nodes or c.get('kind')=='DELTA' and b not in nodes:
            code='STATION_POINT_RETIRED';message='The station evidence refers to a retired or missing physical point.'
        elif c.get('distance_basis')!='ALONG_CENTRELINE':
            code='STATION_DISTANCE_BASIS_REQUIRED';message='Confirm an along-centreline source length; XYZ or page distance is not a station.'
        elif not _source_current(project,c,nodes,sheets):
            code='STATION_SOURCE_STALE';message='Station source content or its physical-point source anchor changed. Review the evidence again.'
        else:
            try:
                value=Decimal(c['value_mm']);tolerance=Decimal(c.get('tolerance_mm','0'))
                if not value.is_finite() or not tolerance.is_finite() or value.copy_abs()>Decimal('1000000000000') or not 0<=tolerance<=100000:
                    raise ValueError()
                if value.as_tuple().exponent < -150 or tolerance.as_tuple().exponent < -150:raise ValueError()
                if c['kind']=='LOCAL_ORIGIN' and value!=0:raise ValueError()
                if c['kind']=='DELTA' and a==b:raise ValueError()
                if c['kind'] not in ('ABSOLUTE','DELTA','LOCAL_ORIGIN','MANUAL_RELATIVE'):raise ValueError()
            except (ValueError,ArithmeticError,KeyError):
                code='STATION_INPUT_INVALID';message='The accepted station value, explicit tolerance or constraint kind is invalid.'
        if code:
            issues.append(_issue(code,message,points,c['id']));blocked.append(set(points));continue
        if not all(topology_assigned(nodes[p]) for p in points):
            issues.append(_issue('STATION_TOPOLOGY_REQUIRED','Assign the referenced points to an explicit engineering route before solving stations.',points,c['id']));continue
        if b and (nodes[a]['line_id'],nodes[a]['route'])!=(nodes[b]['line_id'],nodes[b]['route']):
            issues.append(_issue('STATION_ROUTE_REQUIRED','An along-route station delta requires the same full line and route; cross-route origins need their own explicit datum.',points,c['id']));blocked.append(set(points));continue
        frame=c.get('manual_basis')
        if frame and (frame.get('line_id'),frame.get('route'))!=(nodes[a]['line_id'],nodes[a]['route']):
            issues.append(_issue('STATION_BASIS_REQUIRED','This manual station retains a different line/route datum. Declare the current route station basis explicitly.',points,c['id']));blocked.append(set(points));continue
        evaluation[c['id']]['active']=True;valid.append(c)
    graph={p:[] for p in nodes};anchors={p:[] for p in nodes};origins={}
    for c in sorted(valid,key=lambda c:c['id']):
        a,b=c['from_point_id'],c.get('to_point_id');value=Decimal(c['value_mm']);tol=Decimal(c.get('tolerance_mm','0'))
        if c['kind']=='DELTA':graph[a].append((b,value,tol,c['id']));graph[b].append((a,value.copy_negate(),tol,c['id']))
        else:anchors[a].append(c)
        if c['kind']=='LOCAL_ORIGIN':
            key=basis_id('LOCAL_ORIGIN',nodes[a]['line_id'],nodes[a]['route'],a)
            origins[key]={'point_id':a,'constraint_id':c['id'],'line_id':nodes[a]['line_id'],'route':nodes[a]['route']}
    visited=set();rows={};evidence_groups={}
    with localcontext() as context:
        context.prec=200
        for start in nodes:
            if start in visited:continue
            queue=deque([start]);potential={start:Decimal(0)};uncertainty={start:Decimal(0)};edge_ids=set();conflicts=[];tolerance_review=False
            while queue:
                a=queue.popleft();visited.add(a)
                for b,delta,tol,cid in graph[a]:
                    edge_ids.add(cid);value=potential[a]+delta;limit=uncertainty[a]+tol
                    if b not in potential:potential[b]=value;uncertainty[b]=limit;queue.append(b)
                    elif abs(potential[b]-value)>uncertainty[b]+limit:
                        conflicts.append({'constraint_id':cid,'point_id':b,'residual_mm':str(potential[b]-value)})
                    elif abs(potential[b]-value)>tol:tolerance_review=True
            component=set(potential);direct=sorted((c for p in sorted(component) for c in anchors[p]),key=lambda c:c['id'])
            frames={};all_ids=set(edge_ids)
            for c in direct:
                a=c['from_point_id'];kind=c['kind'];all_ids.add(c['id'])
                if kind=='ABSOLUTE':
                    key=basis_id('ABSOLUTE',nodes[a]['line_id'],nodes[a]['route']);basis='ABSOLUTE';origin=None
                elif kind=='LOCAL_ORIGIN':
                    key=basis_id('LOCAL_ORIGIN',nodes[a]['line_id'],nodes[a]['route'],a);basis='LOCAL_ORIGIN';origin=a
                else:
                    frame=c['manual_basis'];key=frame['basis_id'];basis='LOCAL_ORIGIN';origin=frame.get('basis_point_id')
                    if key not in origins:
                        issues.append(_issue('STATION_BASIS_REQUIRED','The local datum retained by this manual station has no current explicit origin declaration.',[a],c['id']));blocked.append({a});continue
                row=frames.setdefault(key,{'basis':basis,'basis_id':key,'basis_point_id':origin,'anchors':[],'source_anchors':[]})
                row['anchors'].append((Decimal(c['value_mm'])-potential[a],Decimal(c.get('tolerance_mm','0'))+uncertainty[a],c['id']))
                row['source_anchors'].append((Decimal(c['value_mm'])-potential[a],Decimal(c.get('tolerance_mm','0')),c['id']))
            for frame in frames.values():
                first=frame['anchors'][0]
                for value,tol,cid in frame['anchors'][1:]:
                    if abs(value-first[0])>tol+first[1]:conflicts.append({'constraint_id':cid,'residual_mm':str(value-first[0]),'basis_id':frame['basis_id']})
            for frame in frames.values():
                lower=max(value-tol for value,tol,cid in frame['anchors'])
                upper=min(value+tol for value,tol,cid in frame['anchors'])
                if lower>upper:conflicts.append({'basis_id':frame['basis_id'],'reason':'SOURCE_INTERVALS_DISJOINT'})
                choices=[candidate for candidate in frame['source_anchors']
                    if all(abs(candidate[0]-value)<=tol for value,tol,cid in frame['source_anchors'])]
                if not choices:tolerance_review=True
                chosen=choices[0] if choices else frame['source_anchors'][0]
                frame['solution_anchor']=next(a for a in frame['anchors'] if a[2]==chosen[2])
            absolute=next((v for v in frames.values() if v['basis']=='ABSOLUTE'),None)
            local=[v for v in frames.values() if v['basis']=='LOCAL_ORIGIN']
            selected=absolute or (local[0] if len(local)==1 else None)
            source_blocked=any(points&component for points in blocked)
            related={cid:value for cid,value in evaluation.items() if any(canonical_point_id(project,value['constraint'].get(k)) in component for k in ('from_point_id','to_point_id'))}
            fingerprint=digest({'constraints':related,'points':[_point_context(project,nodes[p]) for p in sorted(component)]})
            evidence_groups[fingerprint]={'constraint_ids':sorted(all_ids),'point_ids':sorted(component)}
            if conflicts:issues.append(_issue('STATION_CONSTRAINT_CONFLICT','Along-centreline constraints conflict; no stations were averaged or moved.',component,conflicts=conflicts))
            if tolerance_review and not conflicts:
                issues.append(_issue('STATION_TOLERANCE_REVIEW','Nominal source values require a tolerance reconciliation. No source value was averaged or silently adjusted to fit the chain.',component))
            if not absolute and len(local)>1:
                issues.append(_issue('STATION_MULTIPLE_LOCAL_ORIGINS','More than one local station datum is declared. Retain one origin or supply a source absolute station; no datum was selected by guessing.',component))
            for p in component:
                node=nodes[p];assigned=topology_assigned(node)
                status=('TOPOLOGY_REQUIRED' if not assigned else 'CONFLICT' if conflicts else 'TOLERANCE_REVIEW' if tolerance_review else 'SOURCE_REVIEW_REQUIRED' if source_blocked
                    else 'SOLVED' if selected else 'BASIS_REQUIRED' if len(local)>1 else 'RELATIVE_ONLY' if edge_ids else 'UNKNOWN')
                station=(potential[p]+selected['solution_anchor'][0]) if selected and status=='SOLVED' else None
                if station is not None and abs(station)>Decimal('1000000000000'):
                    status='RANGE_REVIEW';station=None
                    issues.append(_issue('STATION_OUTPUT_RANGE','Solved station exceeds the supported physical range; no value was applied.',[p]))
                relative_frames=[{'basis_id':f['basis_id'],'basis_point_id':f['basis_point_id'],
                    'station_mm':str(potential[p]+f['solution_anchor'][0]) if not conflicts and not tolerance_review else None} for f in local]
                relative=(relative_frames[0]['station_mm'] if len(relative_frames)==1 else str(potential[p]) if edge_ids and not conflicts and not tolerance_review else None)
                rows[p]={'point_id':p,'line_id':node['line_id'],'route':node.get('route'),'status':status,
                    'proposed_station_mm':str(station) if station is not None else None,'station_mm':str(station) if station is not None else None,
                    'absolute_station_mm':str(potential[p]+absolute['solution_anchor'][0]) if absolute and status=='SOLVED' else None,
                    'relative_station_mm':relative,'relative_mm':relative,'relative_frames':relative_frames,
                    'relative_basis_point_id':local[0]['basis_point_id'] if len(local)==1 else start if edge_ids else None,
                    'basis':selected['basis'] if selected else None,'basis_point_id':selected['basis_point_id'] if selected else None,
                    'basis_id':selected['basis_id'] if selected else None,'constraint_ids':sorted(all_ids) if len(all_ids)<=256 else [],
                    'constraint_ids_complete':len(all_ids)<=256,'constraint_group_id':fingerprint,'input_sha256':fingerprint,
                    'tolerance_mm':str(uncertainty[p]+selected['solution_anchor'][1]) if selected and status=='SOLVED' else None,
                    'existing_station_mm':node.get('station_mm'),'can_apply':status=='SOLVED',
                    'retained_manual_anchor':next((deepcopy(c) for c in manual if c['from_point_id']==p),None)}
                if not assigned and node.get('station_mm') is None:
                    issues.append(_issue('STATION_TOPOLOGY_REQUIRED','A visual source point has no accepted ordered route or station basis.',[p]))
                elif status in ('UNKNOWN','RELATIVE_ONLY') and node.get('station_mm') is None:
                    issues.append(_issue('STATION_DATUM_REQUIRED' if edge_ids else 'STATION_UNPROVED',
                        'A delta chain has no accepted absolute station or explicitly declared local origin.' if edge_ids else 'No accepted along-centreline station evidence is available for this point.',[p]))
    # Opposite ends of one component cannot acquire a zero centreline span.
    for c in project.get('physical_model',{}).get('components',[]):
        ends=[v['point_id'] for v in c.get('ports',{}).values() if v]
        if len(ends)!=2 or ends[0]==ends[1] or not all(p in rows for p in ends):continue
        a,b=(rows[p] for p in ends)
        if a['can_apply'] and b['can_apply'] and a['basis_id']==b['basis_id'] and Decimal(a['station_mm'])==Decimal(b['station_mm']):
            issues.append(_issue('STATION_COMPONENT_ENDS_COINCIDENT','Opposite component ends have equal proposed stations. Resolve their source lengths instead of collapsing them.',ends,component_id=c['id']))
            for row in (a,b):row.update(status='CONFLICT',can_apply=False,station_mm=None,proposed_station_mm=None)
    for point,node in nodes.items():
        proof=node.get('station_proof');row=rows[point]
        if proof and (not row['can_apply'] or proof.get('input_sha256')!=row['input_sha256'] or proof.get('basis_id')!=row['basis_id'] or
                      (node.get('station_mm') is None or proof.get('value_mm') is None or Decimal(node['station_mm'])!=Decimal(proof['value_mm']))):
            issues.append(_issue('STATION_SOLUTION_STALE','This stored station was accepted from different source constraints, source anchors or route context. Review/apply current values; the saved value was retained.',[point]))
    dedup={json.dumps(issue,sort_keys=True):issue for issue in issues}
    return {'schema':SCHEMA,'distance_basis':'ALONG_CENTRELINE','points':[rows[point] for point in nodes],'inputs':sorted(valid,key=lambda c:c['id']),
        'input_sha256':global_sha,'evidence_groups':evidence_groups,'can_apply':any(p['can_apply'] for p in rows.values()),'issues':list(dedup.values()),
        'physical_stations_modified':False,'drawing_pixels_used':False,'xyz_distance_used':False}


solve=solve_stations


def apply_station_reasons(project):
    solution=solve_stations(project)
    for node in project['nodes']:
        reasons=sorted({i['code'] for i in solution['issues'] if node['id'] in i.get('point_ids',[]) or i['code']=='STATION_SOLVER_LIMIT'})
        if reasons:node['station_review_reasons']=reasons
        else:node.pop('station_review_reasons',None)
    return solution['issues']


def manual_station_override(node,new_station_mm):
    """An explicit manual edit retires its applied proof without erasing its datum."""
    proof=node.get('station_proof')
    if not proof:
        if new_station_mm is None:return node.pop('manual_station_basis',None) is not None
        return False
    if new_station_mm is not None and node.get('station_mm') is not None and Decimal(new_station_mm)==Decimal(node['station_mm']):return False
    node.setdefault('station_proof_history',[]).append(deepcopy(proof));node.pop('station_proof',None)
    if new_station_mm is None:node.pop('manual_station_basis',None)
    else:node['manual_station_basis']={k:deepcopy(proof.get(k)) for k in ('basis','basis_id','basis_point_id','line_id','route')}
    return True


def station_comparison_basis(node):
    if node.get('station_mm') is None or not node.get('evidence','').strip():return None
    blocking={'STATION_SOLUTION_STALE','STATION_CONSTRAINT_CONFLICT','STATION_SOURCE_STALE','STATION_COMPONENT_ENDS_COINCIDENT',
        'STATION_BASIS_REQUIRED','STATION_ROUTE_REQUIRED','STATION_POINT_RETIRED','STATION_INPUT_INVALID','STATION_SOLVER_LIMIT',
        'STATION_OUTPUT_RANGE','STATION_DISTANCE_BASIS_REQUIRED','STATION_TOLERANCE_REVIEW',
        'STATION_MULTIPLE_LOCAL_ORIGINS','STATION_DATUM_REQUIRED','STATION_TOPOLOGY_REQUIRED','STATION_UNPROVED'}
    if blocking.intersection(node.get('station_review_reasons',[])):return None
    proof=node.get('station_proof') or node.get('manual_station_basis')
    if proof:
        if (proof.get('line_id'),proof.get('route'))!=(node['line_id'],node.get('route')):return None
        if proof.get('value_mm') is not None and Decimal(proof['value_mm'])!=Decimal(node['station_mm']):return None
        return proof.get('basis_id')
    return basis_id('ABSOLUTE',node['line_id'],node.get('route'))


def station_pair_comparable(first,second):
    from packages.engineering import topology_assigned
    if not topology_assigned(first) or not topology_assigned(second):return False
    if (first['line_id'],first['route'])!=(second['line_id'],second['route']):return False
    a,b=station_comparison_basis(first),station_comparison_basis(second)
    return bool(a and a==b)
