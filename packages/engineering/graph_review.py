"""Explicit route review and durable numbering; source geometry is never guessed."""
from collections import Counter
from copy import deepcopy
import hashlib
import json

from packages.engineering import (renumber,topology,topology_assigned,
    source_observations,source_location_reviewed)

SCHEMA='explicit-topology-review-1'
MAX_POINTS=2000


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def canonical(project,point_id):
    seen=set();aliases=project.get('point_aliases',{})
    while point_id in aliases:
        if point_id in seen:raise ValueError('Physical point aliases contain a cycle; reconcile identities before topology review.')
        seen.add(point_id);point_id=aliases[point_id]
    return point_id


def point_context(project,node):
    """Source anchors/proofs bind topology; display bubbles/numbers do not."""
    sheets={s['id']:s for s in project.get('sheets',[])}
    return {**{k:deepcopy(node.get(k)) for k in ('id','line_id','kind','route','order','takeoff_id',
            'source_feature_id','source_feature_role','source_feature_links')},
        'topology_state':node.get('topology_state','ASSIGNED'),
        'source_observations':deepcopy(source_observations(node)),
        'instances':[{'sheet_id':i['sheet_id'],'anchor':deepcopy(i['anchor']),
            'source_sha256':sheets.get(i['sheet_id'],{}).get('sha256'),
            'content_hash':deepcopy(sheets.get(i['sheet_id'],{}).get('content_hash')),
            'registered_line_id':sheets.get(i['sheet_id'],{}).get('line_id'),
            'printed_id':sheets.get(i['sheet_id'],{}).get('printed_id'),
            'identity_verified':sheets.get(i['sheet_id'],{}).get('identity_verified')}
            for i in sorted(node.get('instances',[]),key=lambda i:i['sheet_id'])]}


def _issue(code,message,points=(),line=None,route=None,blocks_apply=False):
    return {'code':code,'severity':'critical','color':'blue','message':message,
        'point_ids':sorted(set(points)),'line_id':line,'route':route,
        'blocks_apply':blocks_apply,'engineering_approved':False}


def audit_graph(project):
    """Read-only structural/geometry diagnostics for every current physical UUID."""
    nodes=project['nodes'];sheets={s['id']:s for s in project.get('sheets',[])};issues=[]
    if len(nodes)>MAX_POINTS:
        graph={'points':[n['id'] for n in nodes],'unassigned_points':[n['id'] for n in nodes if not topology_assigned(n)],
            'edges':[],'source':'not computed: bounded graph review limit exceeded'}
        return {'schema':SCHEMA,'graph':graph,'issues':[_issue('GRAPH_POINT_LIMIT',
            'The bounded graph review supports at most 2,000 physical points.',blocks_apply=True)],
            'summary':{'points':len(nodes),'assigned':0,'unassigned':len(nodes),'edges':len(graph['edges']),
                'connected_assigned':False,'complete':False},'can_apply':False,'engineering_approved':False,
            'structural_issues':[_issue('GRAPH_POINT_LIMIT','The bounded graph review supports at most 2,000 physical points.',blocks_apply=True)],
            'geometry_issues':[]}
    graph=topology(nodes,primary_line=project.get('line_id'))
    counts=Counter(n['id'] for n in nodes)
    for uid,count in sorted(counts.items()):
        if count>1:issues.append(_issue('DUPLICATE_PHYSICAL_POINT_ID','One physical UUID occurs more than once; reconcile the records before numbering.',[uid],blocks_apply=True))
    by_id={n['id']:n for n in nodes};assigned=[n for n in nodes if topology_assigned(n)]
    for retired in sorted(project.get('point_aliases',{})):
        try:target=canonical(project,retired)
        except ValueError:target=None
        if target not in by_id:
            issues.append(_issue('POINT_ALIAS_INVALID','A retained physical identity alias is cyclic or has no current canonical point. Reconcile its history before graph review.',[retired],blocks_apply=True))
    groups={key:sorted((n for n in assigned if (n['line_id'],n['route'])==key),key=lambda n:(n['order'],n['id']))
            for key in {(n['line_id'],n['route']) for n in assigned}}
    for node in nodes:
        uid=node['id'];line=node['line_id'];route=node.get('route')
        if not topology_assigned(node):
            invalid=(node.get('topology_state','ASSIGNED')!='UNASSIGNED' or
                     any(node.get(k) is not None for k in ('route','order','takeoff_id')))
            issues.append(_issue('TOPOLOGY_ASSIGNMENT_INVALID' if invalid else 'TOPOLOGY_UNASSIGNED',
                'Correct the explicit route/order metadata; malformed fields cannot create graph edges.' if invalid else
                'This source location has no accepted route/order; it remains visible without an inferred connection.',
                [uid],line,route,blocks_apply=invalid))
            continue
        observations=source_observations(node)
        if any(sheets.get(i['sheet_id'],{}).get('line_id')!=line for i in node.get('instances',[])):
            issues.append(_issue('POINT_SOURCE_LINE_MISMATCH','The physical point full line differs from a current registered source depiction. Review the register and point identity before accepting graph connectivity.',[uid],line,route,True))
        if (observations and not source_location_reviewed(node,sheets)) or (node.get('origin')=='source-review-profile' and not observations):
            issues.append(_issue('SOURCE_LOCATION_REVIEW_REQUIRED','Inspect every current source depiction independently before accepting its route position.',[uid],line,route,True))
        proof=node.get('topology_proof')
        if proof and (not proof.get('reviewed_by') or not proof.get('evidence') or
                      proof.get('point_context_sha256')!=digest(point_context(project,node))):
            issues.append(_issue('TOPOLOGY_REVIEW_STALE','The source anchor, source inspection or explicit route context changed after topology review. Review the route position again; UUID and stored geometry were retained.',[uid],line,route,True))
        if route=='main' and node.get('takeoff_id'):
            issues.append(_issue('MAIN_TAKEOFF_FORBIDDEN','A main-run point cannot carry a branch takeoff.',[uid],line,route,True))
        if route!='main' and node['kind']=='tee':
            issues.append(_issue('TEE_MAIN_SERIES_REQUIRED','The common tee intersection belongs to the main series, not a second branch tee identity.',[uid],line,route,True))
    for (line,route),members in sorted(groups.items()):
        if len({n['order'] for n in members})!=len(members):
            issues.append(_issue('DUPLICATE_ROUTE_ORDER','Explicit route order is ambiguous; no adjacency was selected by UUID or input-array order.',[n['id'] for n in members],line,route,True))
        if route=='main':continue
        if (line,'main') not in groups:
            issues.append(_issue('MAIN_ROUTE_REQUIRED','A branch requires an explicit main run on the same full line before it can be numbered.',[n['id'] for n in members],line,route,True))
        takeoffs={n.get('takeoff_id') for n in members}
        if len(takeoffs)!=1:
            issues.append(_issue('BRANCH_TAKEOFF_INCONSISTENT','Every member of one branch must identify the same existing main-run tee.',[n['id'] for n in members],line,route,True));continue
        takeoff=next(iter(takeoffs));tee=by_id.get(takeoff)
        if not takeoff:
            issues.append(_issue('BRANCH_TAKEOFF_REQUIRED','Associate this branch with its existing common main-run tee; no takeoff connection was guessed.',[n['id'] for n in members],line,route,True))
        elif not tee or not topology_assigned(tee) or tee['line_id']!=line or tee['route']!='main' or tee['kind']!='tee':
            issues.append(_issue('BRANCH_TAKEOFF_INVALID','The takeoff must be an assigned main-run tee on this exact full line.',[n['id'] for n in members]+([takeoff] if tee else []),line,route,True))
    components=[]
    for line in sorted({n['line_id'] for n in assigned}):
        ids={n['id'] for n in assigned if n['line_id']==line};adjacent={uid:set() for uid in ids}
        for edge in graph['edges']:
            if edge['line_id']==line and edge['from'] in ids and edge['to'] in ids:
                adjacent[edge['from']].add(edge['to']);adjacent[edge['to']].add(edge['from'])
        remaining=set(ids);line_components=[]
        while remaining:
            pending=[min(remaining)];seen=set()
            while pending:
                uid=pending.pop()
                if uid in seen:continue
                seen.add(uid);pending.extend(adjacent[uid]-seen)
            remaining-=seen;line_components.append(sorted(seen))
        components.append({'line_id':line,'components':line_components,'connected':len(line_components)==1})
        if len(line_components)>1:
            issues.append(_issue('GRAPH_DISCONNECTED_SUBGRAPHS','The explicitly assigned route contains disconnected subgraphs; inspect takeoffs and route order instead of inferring a connection.',ids,line,blocks_apply=True))
    from packages.physical.constraints import solve as solve_xyz
    from packages.physical.stations import solve_stations
    structural_issues=deepcopy(issues)
    xyz=solve_xyz(project);coordinates={r['point_id']:r['axes'] for r in xyz['coordinates']}
    frame=project.get('analysis_model',{});origin=by_id.get(frame.get('origin_point_id'))
    main=sorted((n for n in assigned if n['route']=='main' and n['line_id']==project.get('line_id')),key=lambda n:(n['order'],n['id']))
    local_frame=bool(frame.get('local_origin_confirmed') and origin and main and origin['id']==main[0]['id'])
    origin_axes=coordinates.get(origin['id'],{}) if origin else {}
    stations=solve_stations(project);station_stale={p for i in stations['issues'] if i['code']=='STATION_SOLUTION_STALE' for p in i.get('point_ids',[])}
    for node in nodes:
        axes=coordinates.get(node['id'],{})
        absolute=set(axes)=={'X','Y','Z'} and all(v.get('value_mm') is not None for v in axes.values())
        relative=(local_frame and set(axes)=={'X','Y','Z'} and set(origin_axes)=={'X','Y','Z'} and
            all(axes[a].get('relative_mm') is not None and origin_axes[a].get('relative_mm') is not None and
                axes[a].get('relative_basis_point_id')==origin_axes[a].get('relative_basis_point_id') for a in ('X','Y','Z')))
        if not absolute and not relative:
            issues.append(_issue('GRAPH_XYZ_UNPROVED','Complete signed engineering XYZ is not proved for this point; route review never supplies coordinates.',[node['id']],node['line_id'],node.get('route')))
        if node.get('station_mm') is None or not node.get('evidence','').strip() or node.get('verification')=='proposed' or node['id'] in station_stale:
            issues.append(_issue('GRAPH_STATION_UNPROVED','A current accepted along-centreline station/datum is required; route order and XYZ do not supply it.',[node['id']],node['line_id'],node.get('route')))
    connected=bool(assigned) and all(c['connected'] for c in components)
    return {'schema':SCHEMA,'graph':graph,'components':components,'issues':issues,
        'summary':{'points':len(nodes),'assigned':len(assigned),'unassigned':len(nodes)-len(assigned),
            'edges':len(graph['edges']),'lines':len(components),'connected_assigned':connected,
            'complete':bool(nodes) and connected and not issues},
        'can_apply':bool(nodes) and not any(i['blocks_apply'] for i in issues),'engineering_approved':False,
        'structural_issues':structural_issues,'geometry_issues':issues[len(structural_issues):]}


def point_rows(project):
    from packages.physical.source_review import point_label
    sheets={s['id']:s for s in project.get('sheets',[])}
    return [{'point_id':n['id'],'point_label':point_label(n),'line_id':n['line_id'],
        'route':n.get('route'),'order':n.get('order'),'takeoff_id':n.get('takeoff_id'),
        'topology_state':n.get('topology_state','ASSIGNED'),'number':n.get('number'),
        'source_location_reviewed':source_location_reviewed(n,sheets) if source_observations(n) else True,
        'has_source_observations':bool(source_observations(n)),'station_mm':n.get('station_mm'),
        'instances':deepcopy(n.get('instances',[]))} for n in sorted(project['nodes'],key=lambda n:(n['line_id'],n.get('review_label') or n['id']))]


def record_numbering(project,mapping,action,reviewer=None,reviewed_at=None):
    """Retain a complete meaningful map; display-only saves cannot erase it."""
    expected={n['id'] for n in project['nodes']}
    if len(mapping)!=len(expected) or {r['point_id'] for r in mapping}!=expected:
        raise ValueError('A numbering record must include every current physical point, including unassigned points.')
    mapping=sorted(deepcopy(mapping),key=lambda r:r['point_id'])
    previous=project.get('numbering_map',[])
    identities_changed={r['point_id'] for r in previous}!=expected
    aliases=deepcopy(project.get('point_aliases',{}))
    previous_record=(project.get('numbering_history') or [{}])[-1]
    changed=not project.get('numbering_history') or identities_changed or any(r['old']!=r['new'] for r in mapping) or aliases!=previous_record.get('point_aliases',{})
    if not changed:return previous
    by_id={n['id']:n for n in project['nodes']}
    retired=project.get('retired_points',[])
    alias_rows=[]
    for old in sorted(aliases):
        current=canonical(project,old);target=by_id.get(current)
        source=next((r.get('point',r) for r in retired if r.get('point',r).get('id')==old),{})
        alias_rows.append({'retired_point_id':old,'physical_point_id':current,
            'old':source.get('number'),'new':target.get('number') if target else None})
    record={'schema':SCHEMA,'revision':project.get('version',0)+1,'action':action,
        'reviewed_by':reviewer,'reviewed_at':reviewed_at,'mapping':mapping,
        'point_instances':{n['id']:deepcopy(n.get('instances',[])) for n in sorted(project['nodes'],key=lambda n:n['id'])},
        'point_aliases':aliases,'alias_rows':alias_rows}
    record['sha256']=digest(record)
    project['numbering_map']=mapping;project.setdefault('numbering_history',[]).append(record)
    return mapping


def renumber_project(project,action,reviewer=None,reviewed_at=None):
    candidate=deepcopy(project)
    mapping=renumber(candidate['nodes'],primary_line=candidate.get('line_id'))
    result=record_numbering(candidate,mapping,action,reviewer,reviewed_at)
    project.clear();project.update(candidate)
    return result


def record_point_topology_review(project,point_ids,reason,reviewer,reviewed_at):
    """Stamp an explicit direct edit after its source inspection and route checks."""
    if not reviewer or not reviewed_at or not isinstance(reason,str) or len(reason.strip())<10:
        raise ValueError('A topology review needs authenticated decision provenance and explicit route/order evidence.')
    nodes={n['id']:n for n in project['nodes']};sheets={s['id']:s for s in project.get('sheets',[])}
    selected=[]
    for uid in point_ids:
        node=nodes.get(canonical(project,uid))
        if not node or not topology_assigned(node):raise ValueError('Review active explicitly assigned physical points only.')
        if source_observations(node) and not source_location_reviewed(node,sheets):
            raise ValueError('Inspect every current source depiction before confirming its topology.')
        selected.append(node)
    for node in selected:
        old=node.get('topology_proof')
        if old:node.setdefault('topology_proof_history',[]).append(deepcopy(old))
        node['topology_proof']={'schema':SCHEMA,'evidence':reason.strip(),'reviewed_by':reviewer,
            'reviewed_at':reviewed_at,'point_context_sha256':digest(point_context(project,node)),
            'engineering_approved':False}


def _assign(project,assignments,reason,reviewer=None,reviewed_at=None):
    if not isinstance(reason,str) or not 10<=len(reason.strip())<=3000:raise ValueError('Describe the independently inspected route/order evidence.')
    if len(assignments)>MAX_POINTS:raise ValueError('Review at most 2,000 explicit physical points in one batch.')
    ids=[n['id'] for n in project['nodes']]
    if len(ids)!=len(set(ids)):raise ValueError('Resolve duplicate physical UUIDs before topology review.')
    nodes={n['id']:n for n in project['nodes']};seen=set();sheets={s['id']:s for s in project.get('sheets',[])}
    changes=[]
    for row in assignments:
        uid=canonical(project,row['point_id'])
        if uid in seen:raise ValueError('A topology batch cannot repeat a physical UUID or one of its aliases.')
        seen.add(uid);node=nodes.get(uid)
        if not node:raise ValueError('Select current physical points belonging to this project.')
        state=row['topology_state'];route=row.get('route');order=row.get('order');takeoff=row.get('takeoff_id')
        if state=='UNASSIGNED':
            if route is not None or order is not None or takeoff:raise ValueError('An unassigned point has no route/order/takeoff; empty fields never imply a main run or station zero.')
        elif state=='ASSIGNED':
            import re
            if not re.fullmatch(r'main|branch-\d{2}',route or '') or not isinstance(order,int) or isinstance(order,bool) or not 0<=order<=100000:
                raise ValueError('Assign an explicit main/branch route and integral order from 0 to 100000.')
            if source_observations(node) and not source_location_reviewed(node,sheets):
                raise ValueError('Independently inspect every current source depiction before assigning topology; batch review cannot confirm a source location.')
        else:raise ValueError('Choose ASSIGNED or UNASSIGNED explicitly.')
        line=row.get('line_id')
        if not isinstance(line,str) or not 1<=len(line.strip())<=150:raise ValueError('Retain an explicit complete line ID for every topology decision.')
        if any(sheets.get(i['sheet_id'],{}).get('line_id')!=line for i in node.get('instances',[])):
            raise ValueError('A topology decision must retain the full line ID of every source sheet depicting that point.')
        takeoff=canonical(project,takeoff) if takeoff else None
        before={k:deepcopy(node.get(k)) for k in ('line_id','route','order','takeoff_id','topology_state')}
        before['topology_state']=node.get('topology_state','ASSIGNED')
        after={'line_id':line,'route':route,'order':order,'takeoff_id':takeoff,'topology_state':state}
        if state=='ASSIGNED' and not row.get('topology_confirmed'):
            raise ValueError('Explicitly confirm each assigned route position after checking the source and physical sequence.')
        if before!=after or state=='ASSIGNED' and node.get('topology_proof'):
            changes.append({'point_id':uid,'before':before,'after':after})
        if reviewer:
            old=node.get('topology_proof')
            if old:node.setdefault('topology_proof_history',[]).append(deepcopy(old))
        node.update(after)
        if state=='UNASSIGNED':node.pop('topology_proof',None)
        else:
            # A route decision cannot accept a pre-existing proposed numeric
            # station. Null geometry remains null; its source location/type and
            # explicit route may still have been independently reviewed.
            if node.get('station_mm') is None:node['verification']='reviewed'
            node['topology_proof']={'schema':SCHEMA,'evidence':reason.strip(),'reviewed_by':reviewer or 'PREVIEW_ONLY',
                'reviewed_at':reviewed_at,'point_context_sha256':digest(point_context(project,node)),
                'engineering_approved':False}
    return changes


def preview_topology(project,assignments,reason):
    candidate=deepcopy(project);changes=_assign(candidate,assignments,reason)
    numbering_error=None
    try:mapping=renumber(candidate['nodes'],primary_line=candidate.get('line_id'))
    except ValueError as error:
        numbering_error=str(error);mapping=[{'point_id':n['id'],'old':n.get('number'),'new':None} for n in sorted(candidate['nodes'],key=lambda n:n['id'])]
    report=audit_graph(candidate)
    if numbering_error:report['issues'].append(_issue('NUMBERING_REVIEW_REQUIRED',numbering_error,blocks_apply=True));report['can_apply']=False
    fingerprint=digest({'schema':SCHEMA,'revision':project.get('version'),'project_id':project['id'],
        'source_context':[point_context(project,n) for n in sorted(project['nodes'],key=lambda n:n['id'])],
        'point_aliases':project.get('point_aliases',{}),'assignments':assignments,'reason':reason,
        'numbering_map':mapping})
    return {**report,'revision':project.get('version'),'preview_sha256':fingerprint,
        'points':point_rows(candidate),'numbering_map':mapping,'changes':changes,
        'source_locations_confirmed':False,'stations_modified':False,'coordinates_modified':False}


def apply_topology(project,assignments,reason,preview_sha256,reviewer,reviewed_at):
    if not reviewer or not reviewed_at:raise ValueError('An authenticated reviewer and server review time are required.')
    preview=preview_topology(project,assignments,reason)
    if preview['preview_sha256']!=preview_sha256:raise ValueError('The topology preview or source context changed. Preview the exact current decisions again before applying.')
    if not preview['can_apply']:raise ValueError('Resolve the structural/source review blockers before applying this topology batch; missing geometry remains explicitly unknown.')
    # Build the entire update before replacing any point records or maps.
    candidate=deepcopy(project);_assign(candidate,assignments,reason,reviewer,reviewed_at)
    renumber_project(candidate,'Applied explicit source-inspected topology review',reviewer,reviewed_at)
    project.clear();project.update(candidate)
    return preview


def apply_topology_reasons(project):
    report=audit_graph(project)
    for node in project['nodes']:
        reasons=sorted({i['code'] for i in report['issues'] if node['id'] in i['point_ids'] or i['code']=='GRAPH_POINT_LIMIT'})
        if reasons:node['topology_review_reasons']=reasons
        else:node.pop('topology_review_reasons',None)
    return report['issues']
