"""Content-bound review scopes; display changes never become physical proof."""
import hashlib
import json
from copy import deepcopy
from packages.engineering import validate
from packages.physical import audit as component_audit
from packages.physical.constraints import solve as solve_dimensions


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def scopes(project, processing_sources=()):
    result=[]
    native_layout_review=None
    if project.get('native_layout_review'):
        from packages.pdf import accepted_plan_current
        native_layout_review={**{k:project['native_layout_review'].get(k) for k in
            ('input_sha256','placements_sha256','reviewed_by','reviewed_at','reason')},'current':accepted_plan_current(project)}
    partial=project.get('automation',{}).get('partial_pages',{})
    evidence=project.get('automation',{}).get('evidence_pages',[])
    def observed(sheet):
        return (sheet['source_id'] not in processing_sources or
                partial.get(sheet['id'],{}).get('source_sha256')==sheet['sha256'] or
                any(p['sheet_id']==sheet['id'] and p['source_sha256']==sheet['sha256'] for p in evidence))
    def add(kind,key,title,payload,ready,blocking):
        result.append({'key':kind+':'+key,'kind':kind,'title':title,'sha256':digest(payload),
                       'ready':ready,'blocking':sorted(set(blocking)),'payload':payload})
    for sheet in project['sheets']:
        title=sheet.get('printed_id') or sheet['filename']+' · page '+str(sheet['page_index']+1)
        proof={k:sheet.get(k) for k in ('id','line_id','printed_id','width','height','rotation','content_hash')}
        identity=[]
        if not sheet.get('printed_id') or not sheet.get('line_id'):identity.append('DRAWING_IDENTITY_INCOMPLETE')
        if not sheet.get('identity_verified'):identity.append('DRAWING_IDENTITY_UNREVIEWED')
        add('identity',sheet['id'],title+' · identity',proof,True,identity)
        items=[m for m in project['materials'] if m['sheet_id']==sheet['id']]
        missing=[]
        if not items:missing.append('NO_MATERIAL_ROWS')
        for item in items:
            if item.get('verification')!='reviewed':missing.append('MATERIAL_PROPOSALS_UNREVIEWED')
            if item.get('quantity_unit','count')=='unresolved' or (item.get('quantity') is None and item.get('quantity_value') is None):missing.append('SOURCE_QUANTITY_UNKNOWN')
            if item['item_no'].startswith('unreadable-'):missing.append('SOURCE_ITEM_NUMBER_UNREADABLE')
            if item['family'] in ('flange','valve') and not item.get('catalog_match'):missing.append('CATALOG_MATCH_UNRESOLVED')
        material_ids={m['id'] for m in items}
        add('materials',sheet['id'],title+' · materials',{'sheet':proof,'items':items,
            'catalog_reviews':[r for r in project.get('project_catalog_reviews',[]) if r['material_id'] in material_ids],
            'manufacturer_reviews':[r for r in project.get('project_manufacturer_reviews',[]) if r['material_id'] in material_ids],
            'catalog_manifest':project.get('catalog_review',{}).get('catalog_manifest',project.get('catalog_reference_manifest'))},observed(sheet),missing)
        graphics=[]
        for node in project['nodes']:
            for instance in node['instances']:
                if instance['sheet_id']==sheet['id']:
                    graphics.append({'point_id':node['id'],'number':node['number'],'reasons':node.get('reasons',[]),**instance})
        layout=[]
        if sheet.get('axis') is None:layout.append('AXIS_PLACEMENT_UNRESOLVED')
        if any(m['family'] in ('flange','valve') for m in items) and sheet.get('table') is None:layout.append('SCHEDULE_PLACEMENT_UNRESOLVED')
        visible=[{k:m.get(k) for k in ('item_no','description','size','quantity','quantity_value','quantity_unit','catalog_match','catalog_review_state','project_manufacturer_status')} for m in items]
        add('layout',sheet['id'],title+' · presentation',{'sheet':proof,'axis':sheet.get('axis'),
             'table':sheet.get('table'),'graphics':graphics,'schedule':visible,
             'native_layout_review':native_layout_review,
             'notes':[a for a in project.get('annotations',[]) if a['sheet_id']==sheet['id']]},observed(sheet),layout)
    lines=list(dict.fromkeys([s['line_id'] for s in project['sheets']]+[n['line_id'] for n in project['nodes']]))
    component_state=component_audit(project);components=component_state['components']
    dimensional_state=solve_dimensions(project)
    from packages.physical.stations import solve_stations
    station_state=solve_stations(project)
    from packages.physical.source_exceptions import source_exception_report
    source_exception_state=source_exception_report(project)
    sheet_lines={s['id']:s['line_id'] for s in project['sheets']}
    from packages.engineering.graph_review import audit_graph
    graph_state=audit_graph(project)
    for line in lines:
        nodes=[{k:n.get(k) for k in ('id','line_id','route','order','takeoff_id','kind','station_mm','coordinates_mm','dimension_input','evidence','verification','component_ports','topology_state','source_observation','source_observations','source_review_reasons','source_exception_reasons','station_proof','manual_station_basis','topology_proof')}
               for n in project['nodes'] if n['line_id']==line]
        point_ids={n['id'] for n in nodes}
        component_ids={c['id'] for c in components if c['line_id']==line}
        relevant_ids={cid for group in dimensional_state['evidence_groups'].values() if point_ids.intersection(group['points']) for cid in group['constraint_ids']}
        dimensional_checks=[i for i in dimensional_state['issues'] if point_ids.intersection(i.get('point_ids',[])) or i.get('constraint_id') in relevant_ids or i['code'] in ('DIMENSION_SOLVER_LIMIT','DIMENSION_SOLUTION_STALE')]
        station_checks=[i for i in station_state['issues'] if point_ids.intersection(i.get('point_ids',[])) or i['code']=='STATION_SOLVER_LIMIT']
        source_checks=[i for i in source_exception_state['all'] if sheet_lines.get(i.get('sheet_id'))==line or point_ids.intersection(i.get('point_ids',[]))]
        source_exception_ids={i['id'] for i in source_checks}
        graph_checks=[i for i in graph_state['issues'] if i.get('line_id')==line or point_ids.intersection(i.get('point_ids',[])) or i['code']=='GRAPH_POINT_LIMIT']
        missing=[]
        if not nodes:missing.append('NO_PHYSICAL_NODES')
        if any(n['station_mm'] is None or not n.get('evidence') for n in nodes):missing.append('PHYSICAL_STATIONS_UNVERIFIED')
        if any(n.get('verification')=='proposed' for n in nodes):missing.append('NODE_PROPOSALS_UNREVIEWED')
        missing.extend(i['code'] for i in component_state['issues'] if i.get('component_id') in component_ids)
        missing.extend(i['code'] for i in dimensional_checks)
        missing.extend(i['code'] for i in station_checks)
        missing.extend(i['code'] for i in source_checks if i['active'])
        missing.extend(i['code'] for i in graph_checks)
        from packages.engineering.continuations import audit as continuation_audit
        continuation_checks=[i for i in continuation_audit(project) if i['line_id']==line]
        missing.extend(i['code'] for i in continuation_checks)
        if any(any(v is None for v in edge['delta_mm'].values()) for edge in dimensional_state['elements'] if edge['line_id']==line):missing.append('SIGNED_XYZ_UNRESOLVED')
        add('geometry',line,'Line '+line+' · physical model',{'nodes':nodes,
              'elements':[e for e in project.get('analysis_model',{}).get('elements',[]) if e.get('from_point_id',e.get('from')) in point_ids or e.get('to_point_id',e.get('to')) in point_ids],
              'continuations':[c for c in project.get('continuations',[]) if c.get('point_id') in point_ids or c.get('line_id')==line],
              'continuation_checks':continuation_checks,
              'components':[c for c in components if c['line_id']==line],
              'component_association_checks':[i for i in component_state['issues'] if i.get('component_id') in component_ids],
              'dimensional_constraints':[c for c in project.get('physical_model',{}).get('constraints',[]) if c.get('from_point_id') in point_ids or c.get('to_point_id') in point_ids],
              'dimensional_inputs':[c for c in dimensional_state['inputs'] if c['id'] in relevant_ids],
              'dimensional_checks':dimensional_checks,
              'station_constraints':[c for c in project.get('physical_model',{}).get('station_constraints',[]) if c.get('from_point_id') in point_ids or c.get('to_point_id') in point_ids],
              'station_checks':station_checks,
              'source_exceptions':source_checks,
              'source_exception_reviews':[r for r in source_exception_state['reviews'] if r['exception_id'] in source_exception_ids],
              'topology_checks':graph_checks,
              'model_frame':{k:project.get('analysis_model',{}).get(k) for k in ('local_origin_confirmed','origin_point_id','vertical_axis','piping_code_id','ambient_temperature_c')}},
              all(observed(s) for s in project['sheets'] if s['line_id']==line),missing)
    return result


def issues(project):
    output=[]
    numbers={n.get('number'):n['id'] for n in project['nodes']}
    for value in validate(deepcopy(project)):
        target={k:value.get(k) for k in ('code','sheet_id','material_id','point_id','evidence_id','element_id','line_id','route','message')}
        if value.get('node') in numbers:target['point_id']=numbers[value['node']]
        output.append({**value,'id':digest(target)[:24]})
    return output


def snapshot_hash(project):
    # Status/approval receipts are consequences of the decision, not its input.
    return digest({k:v for k,v in project.items() if k not in ('issues','status','review_approval','updated','graph')})
