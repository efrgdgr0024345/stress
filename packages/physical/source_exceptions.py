"""Source exceptions follow actual proof; a recorded explanation is not approval.

The exact reviewed-PDF profile supplies immutable source observations. Active
exceptions are derived from current material/component/dimensional proof. Human
source dispositions are append-only, source-bound review records; they cannot
waive required COD/classification facts or manufacture stations.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import re

from packages.physical import identity,requirements

DECISIONS=('CONFIRM_WITNESS_MAPPING','REOPEN','RETAIN_UNRESOLVED')
MAX_REVIEWS=1000


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _canonical(project,point_id):
    aliases=project.get('point_aliases',{});seen=set()
    while point_id in aliases:
        if point_id in seen:return None
        seen.add(point_id);point_id=aliases[point_id]
    return point_id


def _catalog(project):
    """Merge current source facts with retained registry entries for stale review."""
    from packages.physical.source_review import source_profile
    state=project.get('source_review',{})
    if not state.get('prepared'):return []
    profile=source_profile()
    entries={entry['id']:deepcopy(entry) for entry in state.get('exception_registry',[])}
    if not profile:return list(entries.values())
    sheets={s['page_index']:s for s in project.get('sheets',[]) if s.get('sha256')==profile['source_sha256']}
    groups=(('INTERFACE',profile.get('exceptions',[])),
            ('STATION_DIMENSION',profile.get('station_source_facts',{}).get('exceptions',[])))
    for group,observations in groups:
        for original in observations:
            sheet=sheets.get(original['page_index'])
            if not sheet:continue
            uid=identity(project['id'],original['id'])
            entries[uid]={**deepcopy(original),'id':uid,'source_exception_id':original['id'],
                'source_group':group,'sheet_id':sheet['id'],'source_sha256':profile['source_sha256'],
                'source_content_hash':deepcopy(sheet.get('content_hash'))}
    return list(entries.values())


def _source_current(entry,sheets):
    sheet=sheets.get(entry.get('sheet_id'))
    # This curated profile is exclusively for the immutable exact reviewed PDF.
    return bool(sheet and sheet.get('sha256')==entry.get('source_sha256') and
        (entry.get('source_content_hash')==sheet.get('content_hash') if entry.get('source_content_hash') else True))


def _material_items(entry):
    raw=str(entry.get('material_item_no',''))
    return set(re.findall(r'\d+',raw))


def _linked_points(project,entry,components=None):
    state=project.get('source_review',{});mapping=state.get('observation_points',{})
    nodes={n['id']:n for n in project['nodes']};points=set()
    for key in ('endpoint_a_observation_id','endpoint_b_observation_id'):
        uid=_canonical(project,mapping.get(entry.get(key)))
        if uid in nodes:points.add(uid)
    items=_material_items(entry)
    for component in components if components is not None else requirements(project)[0]:
        if component['sheet_id']==entry.get('sheet_id') and component['item_no'] in items:
            if entry.get('occurrence') is not None and component['occurrence']!=entry['occurrence']:continue
            if entry['code'] in ('COINCIDENT_SUPPORT_REVIEW_REQUIRED','COINCIDENT_SUPPORT_STATION_UNCONFIRMED') and component['occurrence']!=1:continue
            if entry['code']=='PROCESS_INTERFACE_BOUNDARY_REVIEW_REQUIRED' and component['item_no']=='9' and component['occurrence']!=3:continue
            for port,value in component['ports'].items():
                if not value or entry.get('port') and port!=entry['port']:continue
                if entry['code']=='DASHED_BOUNDARY_INTERFACE_REVIEW_REQUIRED' and port!='process_out':continue
                if entry['code']=='PROCESS_INTERFACE_BOUNDARY_REVIEW_REQUIRED' and component['item_no']=='9' and port!='process_out':continue
                points.add(_canonical(project,value['point_id']))
    return sorted(p for p in points if p in nodes)


def _context(project,entry,components=None):
    nodes={n['id']:n for n in project['nodes']};sheets={s['id']:s for s in project.get('sheets',[])}
    items=_material_items(entry);point_ids=_linked_points(project,entry,components)
    sheet=sheets.get(entry.get('sheet_id'))
    material_fields=('id','sheet_id','item_no','family','description','size','quantity','quantity_unit','verification','evidence','source_sha256')
    materials=[{k:deepcopy(m.get(k)) for k in material_fields} for m in project.get('materials',[])
               if m.get('sheet_id')==entry.get('sheet_id') and m.get('item_no') in items]
    components=[deepcopy(c) for c in (components if components is not None else requirements(project)[0]) if c['sheet_id']==entry.get('sheet_id') and c['item_no'] in items]
    point_context=[]
    for point_id in point_ids:
        node=nodes[point_id]
        point_context.append({**{k:deepcopy(node.get(k)) for k in ('id','line_id','kind','route','order','topology_state',
            'station_mm','station_proof','verification','evidence','source_observation')},
            'instances':[{'sheet_id':i['sheet_id'],'anchor':deepcopy(i['anchor'])} for i in node.get('instances',[])]})
    result={'source_exception':entry,'source_sheet':{k:deepcopy((sheet or {}).get(k)) for k in
            ('id','sha256','content_hash','line_id','printed_id','identity_verified')},
        'materials':materials,'components':components,
        'points':point_context,
        'coordinate_inputs':[deepcopy(c) for c in project.get('physical_model',{}).get('constraints',[])
            if c.get('from_point_id') in point_ids or c.get('to_point_id') in point_ids],
        'station_inputs':[deepcopy(c) for c in project.get('physical_model',{}).get('station_constraints',[])
            if c.get('from_point_id') in point_ids or c.get('to_point_id') in point_ids]}
    if entry['code'] in ('DASHED_BOUNDARY_INTERFACE_REVIEW_REQUIRED','CONTINUATION_INTERFACE_REVIEW_REQUIRED'):
        from packages.engineering.continuations import source_review_states
        label='S1-CONT-SHEET2' if entry['code']=='DASHED_BOUNDARY_INTERFACE_REVIEW_REQUIRED' else 'S2-CONT-SHEET1'
        result['continuation_source_states']=[{k:deepcopy(v) for k,v in state.items() if k!='point_label'}
            for state in source_review_states(project).values() if state.get('source_label')==label]
    return result


def _point_reviewed(node,sheets):
    from packages.engineering import source_location_reviewed
    if node.get('source_observation'):return source_location_reviewed(node,sheets)
    return node.get('origin')!='source-review-profile' and node.get('verification')=='reviewed' and len(node.get('evidence','').strip())>=10


def _port_proof(project,component,key):
    if component.get('verification')!='reviewed' or not component.get('reviewed_by'):return None
    association=component.get('ports',{}).get(key)
    if not association:return None
    proof=association.get('proof',{})
    if proof.get('verification') not in (None,'reviewed') or not proof.get('reviewed_by') or len(proof.get('evidence','').strip())<10:return None
    sheets={s['id']:s for s in project.get('sheets',[])};sheet=sheets.get(proof.get('sheet_id'))
    node=next((n for n in project['nodes'] if n['id']==_canonical(project,association.get('point_id'))),None)
    if not sheet or not node or node['line_id']!=component['line_id']:return None
    if proof.get('source_sha256')!=sheet.get('sha256'):return None
    if proof.get('content_hash') and proof['content_hash']!=sheet.get('content_hash'):return None
    instance=next((i for i in node.get('instances',[]) if i['sheet_id']==sheet['id']),None)
    box=proof.get('bbox',[])
    if not instance or len(box)!=4 or not box[0]<=instance['anchor'][0]<=box[2] or not box[1]<=instance['anchor'][1]<=box[3]:return None
    if not _point_reviewed(node,sheets):return None
    return node,proof


def _current_station(project,node,cache):
    """Fresh proof evaluation; cached drawing colour/reason fields are not proof."""
    if node.get('station_mm') is None:return None
    from packages.physical.stations import solve_stations
    if 'stations' not in cache:cache['stations']=solve_stations(project)
    solution=cache['stations'];row=next((r for r in solution['points'] if r['point_id']==node['id']),None)
    if not row or not row['can_apply'] or not row.get('basis_id') or row.get('station_mm') is None:return None
    if any(issue['code']=='STATION_SOLVER_LIMIT' or node['id'] in issue.get('point_ids',[]) for issue in solution['issues']):return None
    try:
        if not Decimal(row['station_mm']).is_finite() or Decimal(row['station_mm'])!=Decimal(node['station_mm']):return None
    except (ValueError,ArithmeticError):return None
    return row


def _continuation_disposition(project,label):
    from packages.engineering.continuations import source_review_states,independent_source_coordinates
    state=next((s for s in source_review_states(project).values() if s.get('source_label')==label),None)
    if not state or not state.get('current') or state.get('stale') or state.get('verification')!='reviewed':return None
    state={k:deepcopy(v) for k,v in state.items() if k!='point_label'}
    if state['status'] in ('ENDPOINT_EXCEPTION','REJECTED_MATCH'):
        return {'method':'CURRENT_REVIEWED_PEER_REJECTION_RETAINED_SEPARATE','state':deepcopy(state),
                'physical_identity_accepted':False,'engineering_approved':False}
    if state['status']!='SHARED_IDENTITY_REVIEWED':return None
    node=next((n for n in project['nodes'] if n['id']==state.get('point_id')),None)
    sheets={s['id']:s for s in project.get('sheets',[])}
    if not node or not _point_reviewed(node,sheets):return None
    independent=independent_source_coordinates(project,node)
    if independent['missing'] or independent['conflicting_axes'] or any(v is None for v in independent['coordinates'].values()):return None
    return {'method':'CURRENT_REVIEWED_EXACT_CONTINUATION_SOURCE_PROOF','state':deepcopy(state),
            'point_id':node['id'],'engineering_approved':False}


def _derived_resolution(project,entry,cache):
    materials=[m for m in project.get('materials',[]) if m.get('sheet_id')==entry.get('sheet_id') and m.get('item_no') in _material_items(entry)]
    code=entry['code'];components=cache['components']
    if code=='SOURCE_INVENTORY_METADATA_CORRECTION_REQUIRED':
        material=next(iter(materials),None)
        if material and material['family']=='elbow' and material.get('quantity_unit')=='count' and type(material.get('quantity')) is int and material['quantity']==2:
            from packages.engineering.continuations import size_value
            try:size_ok=size_value(material.get('size',''))=='8'
            except (ValueError,ZeroDivisionError):size_ok=False
            if size_ok:return {'method':'CURRENT_SOURCE_METADATA_PRESENT','material_id':material['id'],'quantity':2,'size':'8','engineering_approved':False}
    if code=='INSTRUMENT_CLASSIFICATION_REVIEW_REQUIRED':
        for material in materials:
            if material.get('verification')!='reviewed' or len(material.get('evidence','').strip())<10:continue
            kinds={c['kind'] for c in components if c['material_id']==material['id']}
            if ((material['family']=='valve' and kinds=={'valve'}) or
                (material['family']=='instrument' and kinds=={'inline_instrument'})):
                return {'method':'CURRENT_HUMAN_COMPONENT_CLASSIFICATION','material_id':material['id'],'family':material['family'],'engineering_approved':False}
    if code=='UNCONFIRMED_ELBOW_COD':
        from packages.physical.cod import CONVENTION
        from packages.physical.constraints import solve
        target=next((c for c in components if c['sheet_id']==entry.get('sheet_id') and
            c['item_no']==str(entry.get('material_item_no')) and c['occurrence']==entry.get('occurrence') and c['kind']=='elbow'),None)
        accepted=_port_proof(project,target,'theoretical_cod') if target else None
        if not accepted:return None
        node,proof=accepted
        if node['kind']!='elbow' or proof.get('kind')!='DIMENSION_CHAIN_COD' or proof.get('dimension_convention_kind')!=CONVENTION or len(proof.get('dimension_convention','').strip())<10:return None
        if 'xyz' not in cache:cache['xyz']=solve(project)
        solution=cache['xyz'];coordinate=next((r for r in solution['coordinates'] if r['point_id']==node['id']),None)
        if not coordinate or set(coordinate.get('axes',{}))!={'X','Y','Z'} or any(v.get('value_mm') is None for v in coordinate['axes'].values()):return None
        constraints={c['id']:c for c in project.get('physical_model',{}).get('constraints',[])}
        for issue in solution['issues']:
            c=constraints.get(issue.get('constraint_id'),{})
            if issue['code']=='DIMENSION_SOLVER_LIMIT' or node['id'] in set(issue.get('point_ids',[]))|{c.get('from_point_id'),c.get('to_point_id')}:return None
        return {'method':'CURRENT_THEORETICAL_COD_SOURCE_AND_XYZ_PROOF','component_id':target['id'],'point_id':node['id'],
            'coordinates_mm':{axis:v['value_mm'] for axis,v in coordinate['axes'].items()},'engineering_approved':False}
    if code in ('COINCIDENT_SUPPORT_REVIEW_REQUIRED','COINCIDENT_SUPPORT_STATION_UNCONFIRMED'):
        candidates=[c for c in components if c['sheet_id']==entry.get('sheet_id') and c['kind']=='support' and
            c['occurrence']==1 and c['item_no'] in ('13','14')]
        accepted=[_port_proof(project,c,'support_station') for c in candidates]
        if len(accepted)==2 and all(accepted):
            first,second=accepted[0][0],accepted[1][0]
            if first['id']==second['id'] and _current_station(project,first,cache):
                return {'method':'CURRENT_SHARED_SUPPORT_STATION_PROOF','point_id':first['id'],'component_ids':[c['id'] for c in candidates],
                    'station_mm':first['station_mm'],'engineering_approved':False}
    if code=='PROCESS_INTERFACE_BOUNDARY_REVIEW_REQUIRED':
        dbb=next((c for c in components if c['sheet_id']==entry['sheet_id'] and c['item_no']=='9' and c['occurrence']==3 and c['kind']=='valve'),None)
        pit=next((c for c in components if c['sheet_id']==entry['sheet_id'] and c['item_no']=='12' and c['kind']=='single_instrument'),None)
        accepted=([_port_proof(project,dbb,key) for key in ('process_in','process_out')] +
                  [_port_proof(project,pit,'process_connection')]) if dbb and pit else []
        if len(accepted)==3 and all(accepted):
            station_rows=[_current_station(project,pair[0],cache) for pair in accepted]
            if all(station_rows) and len({r['basis_id'] for r in station_rows})==1:
                first,last=accepted[1][0],accepted[2][0]
                if first['id']==last['id'] or Decimal(first['station_mm'])!=Decimal(last['station_mm']):
                    return {'method':'CURRENT_REVIEWED_PROCESS_INTERFACES_AND_STATIONS','component_ids':[dbb['id'],pit['id']],
                        'point_ids':list(dict.fromkeys(pair[0]['id'] for pair in accepted)),'engineering_approved':False}
    if code=='CONTINUATION_INTERFACE_REVIEW_REQUIRED':
        disposition=_continuation_disposition(project,'S2-CONT-SHEET1')
        if disposition:return disposition
    if code=='DASHED_BOUNDARY_INTERFACE_REVIEW_REQUIRED':
        target=next((c for c in components if c['sheet_id']==entry['sheet_id'] and c['item_no']=='6' and c['kind']=='valve'),None)
        accepted=_port_proof(project,target,'process_out') if target else None
        disposition=_continuation_disposition(project,'S1-CONT-SHEET2')
        if accepted and disposition:
            if disposition['method']=='CURRENT_REVIEWED_EXACT_CONTINUATION_SOURCE_PROOF' and disposition['point_id']!=accepted[0]['id']:return None
            return {'method':'CURRENT_DASHED_PROCESS_INTERFACE_AND_PEER_DISPOSITION','point_id':accepted[0]['id'],
                    'component_id':target['id'],'continuation_disposition':disposition,'engineering_approved':False}
    return None


def _mapping_reference(project,entry,constraint_ids):
    if entry.get('code')!='DIMENSION_WITNESS_MAPPING_UNCONFIRMED':raise ValueError('This source exception cannot be waived with a station mapping; supply its actual required engineering proof.')
    if len(constraint_ids)!=1:raise ValueError('Select exactly one current accepted along-centreline delta matching the printed source span.')
    from packages.physical.stations import station_constraints,_source_current
    from packages.engineering.coordinates import coordinate_value
    constraint=next((c for c in station_constraints(project) if c['id']==constraint_ids[0]),None)
    if not constraint or constraint.get('verification')!='reviewed' or not constraint.get('reviewed_by') or not constraint.get('reviewed_at') or len(constraint.get('evidence','').strip())<10:
        raise ValueError('The selected station delta has no current explicit reviewer/source evidence.')
    if constraint.get('kind')!='DELTA' or constraint.get('distance_basis')!='ALONG_CENTRELINE' or constraint.get('sheet_id')!=entry['sheet_id']:
        raise ValueError('Witness mapping requires a same-source along-centreline delta, not XYZ distance or an unrelated datum.')
    nodes={n['id']:n for n in project['nodes']};sheets={s['id']:s for s in project['sheets']}
    a,b=(_canonical(project,constraint.get(k)) for k in ('from_point_id','to_point_id'))
    if a not in nodes or b not in nodes or a==b or not _source_current(project,constraint,nodes,sheets):
        raise ValueError('The station delta or its physical-point source anchors are stale or missing.')
    if constraint.get('source_sha256')!=entry['source_sha256']:raise ValueError('The delta belongs to a different source PDF.')
    try:
        printed=coordinate_value(entry['source_text'],'X',constraint.get('source_format','STANDARD'))
        if printed.get('source_direction') is not None:raise ValueError()
        value=Decimal(printed['value_mm']);actual=Decimal(constraint['value_mm'])
        if not value.is_finite() or not actual.is_finite() or value<=0 or abs(actual)!=value:raise ValueError()
    except (ValueError,ArithmeticError,KeyError):
        raise ValueError('The selected source convention/value does not retain the exact original printed dimension.') from None
    return {'constraint':deepcopy(constraint),'point_context':[
        {'id':nodes[p]['id'],'line_id':nodes[p]['line_id'],'kind':nodes[p]['kind'],
         'sources':[{'sheet_id':i['sheet_id'],'anchor':deepcopy(i['anchor']),
                     'source_sha256':sheets.get(i['sheet_id'],{}).get('sha256'),
                     'content_hash':deepcopy(sheets.get(i['sheet_id'],{}).get('content_hash'))}
                    for i in nodes[p].get('instances',[])]} for p in (a,b)]}


def source_exception_report(project):
    """Read-only report; source/engineering changes invalidate old dispositions."""
    entries=_catalog(project);sheets={s['id']:s for s in project.get('sheets',[])}
    raw_reviews=project.get('source_exception_reviews',[]);latest={r['exception_id']:r for r in raw_reviews}
    all_rows=[];cache={'components':requirements(project)[0]};review_states={}
    for entry in entries:
        source_current=_source_current(entry,sheets);context_sha=_digest(_context(project,entry,cache['components']));resolution=_derived_resolution(project,entry,cache) if source_current else None
        latest_review=latest.get(entry['id']);current=False;mapping=None
        if latest_review and source_current and latest_review.get('source_context_sha256')==context_sha:
            current=True
            if latest_review['decision']=='CONFIRM_WITNESS_MAPPING':
                try:
                    mapping=_mapping_reference(project,entry,latest_review.get('constraint_ids',[]))
                    current=_digest(mapping)==latest_review.get('mapping_sha256')
                except ValueError:current=False
            if current:
                if latest_review['decision']=='CONFIRM_WITNESS_MAPPING':resolution={'method':'EXPLICIT_CURRENT_SOURCE_WITNESS_MAPPING','constraint_ids':latest_review['constraint_ids'],'engineering_approved':False}
                else:resolution=None
        status=('SOURCE_STALE' if not source_current else 'RESOLVED_BY_CURRENT_PROOF' if resolution else
                'RETAINED_UNRESOLVED' if current and latest_review['decision']=='RETAIN_UNRESOLVED' else
                'REOPENED' if current and latest_review['decision']=='REOPEN' else
                'REVIEW_STALE' if latest_review and not current else 'REVIEW_REQUIRED')
        active=not bool(resolution)
        decisions=['REOPEN','RETAIN_UNRESOLVED']
        if entry['code']=='DIMENSION_WITNESS_MAPPING_UNCONFIRMED' and source_current:decisions.insert(0,'CONFIRM_WITNESS_MAPPING')
        points=_linked_points(project,entry,cache['components']);materials=[m for m in project.get('materials',[]) if m.get('sheet_id')==entry.get('sheet_id') and m.get('item_no') in _material_items(entry)]
        row={**deepcopy(entry),'source_bbox':deepcopy(entry.get('source_region_bbox') or entry.get('bbox')),
            'material_id':materials[0]['id'] if len(materials)==1 else None,'material_ids':[m['id'] for m in materials],
            'point_ids':points,'physical_point_id':points[0] if len(points)==1 else None,
            'source_current':source_current,'source_context_sha256':context_sha,'active':active,'current':source_current,
            'status':status,'severity':'critical' if active else 'info','color':'blue' if active else None,
            'evidence':entry.get('evidence','Source proof remains unresolved.'),'message':entry.get('evidence','Source proof remains unresolved.'),
            'available_decisions':decisions,'resolution':resolution,'engineering_approved':False,
            'latest_review':{**deepcopy(latest_review),'current':current,'stale':not current} if latest_review else None}
        all_rows.append(row)
        if latest_review:review_states[latest_review['id']]=current
    reviews=[{**deepcopy(r),'is_latest':latest.get(r['exception_id'],{}).get('id')==r['id'],
              'current':review_states.get(r['id'],False),'stale':not review_states.get(r['id'],False)} for r in raw_reviews]
    return {'active':[r for r in all_rows if r['active']],'resolved':[r for r in all_rows if not r['active']],
            'all':all_rows,'reviews':reviews,'engineering_approved':False}


def refresh_source_exceptions(project):
    """Persist the derived active view without modifying model facts or reviews."""
    state=project.get('source_review')
    if not state or not state.get('prepared'):return []
    state['exception_registry']=_catalog(project)
    report=source_exception_report(project)
    state['exceptions']=deepcopy(report['active']);state['resolved_exceptions']=deepcopy(report['resolved'])
    state['exception_summary']={'active':len(report['active']),'resolved':len(report['resolved']),'review_records':len(report['reviews'])}
    point_reasons={n['id']:set() for n in project['nodes']}
    for entry in report['active']:
        for point_id in entry['point_ids']:
            if point_id in point_reasons:point_reasons[point_id].add(entry['code'])
    for node in project['nodes']:
        if point_reasons[node['id']]:node['source_exception_reasons']=sorted(point_reasons[node['id']])
        else:node.pop('source_exception_reasons',None)
    return state['exceptions']


def record_source_exception_decision(project,exception_id,decision,evidence,reviewer,reviewed_at,constraint_ids=None,source_context_sha256=None):
    """Record source review only; never accept/move engineering data or approval."""
    if decision not in DECISIONS:raise ValueError('Unsupported source exception decision.')
    if not isinstance(evidence,str) or not 10<=len(evidence.strip())<=3000:raise ValueError('Describe the actual source evidence or why the missing facts remain unresolved.')
    if isinstance(reviewer,dict):
        if reviewer.get('role') not in ('admin','engineer'):raise ValueError('Only an authorised engineer/editor may record a source exception decision.')
        reviewer=reviewer.get('id')
    if not isinstance(reviewer,str) or not reviewer.strip() or not reviewed_at:raise ValueError('Authenticated reviewer identity and server review time are required.')
    report=source_exception_report(project);target=next((r for r in report['all'] if r['id']==exception_id),None)
    if not target:raise ValueError('Current source exception not found.')
    if not target['source_current']:raise ValueError('The source exception refers to changed source evidence; refresh its source observations before reviewing it.')
    if source_context_sha256 is not None and source_context_sha256!=target['source_context_sha256']:raise ValueError('Source exception context changed; reload and inspect the current source proof.')
    constraints=list(constraint_ids or [])
    if decision!='CONFIRM_WITNESS_MAPPING' and constraints:raise ValueError('Only witness mapping may reference a station constraint.')
    mapping=_mapping_reference(project,target,constraints) if decision=='CONFIRM_WITNESS_MAPPING' else None
    reviews=project.setdefault('source_exception_reviews',[])
    if len(reviews)>=MAX_REVIEWS:raise ValueError('Source exception review allowance reached; retain its complete history for engineering review.')
    review={'id':identity(project['id'],'source-exception-review',exception_id,len(reviews)+1,str(reviewed_at)),
        'exception_id':exception_id,'decision':decision,'evidence':evidence.strip(),'reviewed_by':reviewer,
        'reviewed_at':reviewed_at,'source_context_sha256':target['source_context_sha256'],'constraint_ids':constraints,
        'mapping_sha256':_digest(mapping) if mapping else None,'engineering_approved':False}
    reviews.append(review);refresh_source_exceptions(project)
    return deepcopy(review)
