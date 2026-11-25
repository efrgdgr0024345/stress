"""The website and exported workbook share these exact physical-model tables."""
from packages.physical import audit,POLICIES
from packages.physical.constraints import solve


def tables(project):
    state=audit(project);solution=solve(project);nodes={n['id']:n for n in project['nodes']}
    sheets={s['id']:s for s in project['sheets']}
    def table(name,columns,rows):return {'name':name,'columns':[{'key':k,'label':t,'kind':v} for k,t,v in columns],'rows':rows}
    ports=[]
    for c in state['components']:
        for key in POLICIES[c['kind']]['ports'] or ('connection_type_unconfirmed',):
            value=c['ports'].get(key);n=nodes.get(value.get('point_id')) if value else None;proof=value.get('proof',{}) if value else {}
            port_issues=[i for i in state['issues'] if i.get('component_id')==c['id'] and i.get('port') in (None,key)]
            codes=sorted({i['code'] for i in port_issues})
            ports.append({'id':c['id']+':'+key,'component_id':c['id'],'material_id':c['material_id'],
                'item':c['item_no'],'occurrence':c['occurrence'],'line':c['line_id'],'kind':c['kind'],
                'port':key,'node':n.get('number') if n else None,'point_id':n['id'] if n else None,
                'station':n.get('station_mm') if n else None,'state':'REVIEW REQUIRED' if codes else 'SOURCE ASSOCIATION REVIEWED',
                'reasons':', '.join(codes),'evidence':proof.get('evidence'),'proof_kind':proof.get('kind'),
                'sheet_id':proof.get('sheet_id') or c['sheet_id'], 'review_label':n.get('review_label') if n else None,
                'location_state':'SOURCE POINT PROPOSED' if n and n.get('source_observation',{}).get('verification')!='reviewed' else 'SOURCE LOCATION REVIEWED' if n else 'UNLOCATED — EXPLICIT EXCEPTION',
                'source_sha':proof.get('source_sha256') or sheets.get(c['sheet_id'],{}).get('sha256'),
                'source_bbox':str(proof.get('bbox')) if proof.get('bbox') else None,
                'exception_ids':', '.join(i['id'] for i in port_issues)})
    dimensions=[]
    for c in project.get('physical_model',{}).get('constraints',[]):
        dimensions.append({'id':c['id'],'kind':c['kind'],'axis':c['axis'],'from_node':nodes.get(c['from_point_id'],{}).get('number'),
            'to_node':nodes.get(c.get('to_point_id'),{}).get('number'),'source_text':c['source_text'],
            'value':c['value_mm'],'tolerance':c.get('tolerance_mm'),'state':c['verification'],
            'source_sha':c.get('source_sha256'),'sheet':sheets.get(c.get('sheet_id'),{}).get('printed_id') or c.get('sheet_id'),
            'evidence':c['evidence']})
    coordinates=[]
    for point in solution['coordinates']:
        n=nodes[point['point_id']]
        for axis,value in point['axes'].items():
            coordinates.append({'id':point['point_id']+':'+axis,'point_id':point['point_id'],'node':n.get('number'),
                'line':n['line_id'],'axis':axis,'coordinate':value['value_mm'],'relative':value['relative_mm'],
                'basis':nodes.get(value['relative_basis_point_id'],{}).get('number'),'state':value['status'],
                'tolerance':value['tolerance_mm'],'evidence_group':value['evidence_group']})
    continuations=[]
    from packages.engineering.continuations import audit as continuation_audit
    checks=continuation_audit(project)
    def display(uid):return nodes.get(project.get('point_aliases',{}).get(uid,uid),{}).get('number')
    for c in project.get('continuations',[]):
        reasons=', '.join(i['code'] for i in checks if i['continuation_id']==c['id'])
        for axis in ('X','Y','Z'):
            continuations.append({'id':c['id']+':'+axis,'continuation_id':c['id'],'line':c['line_id'],
                'left':display(c['left_point_id']),'right':display(c['right_point_id']),
                'shared':nodes.get(c.get('point_id'),{}).get('number'),'axis':axis,'delta':c['delta_mm'].get(axis),
                'left_coordinate':c.get('coordinates',{}).get(c['left_point_id'],{}).get(axis),
                'right_coordinate':c.get('coordinates',{}).get(c['right_point_id'],{}).get(axis),
                'state':c['status'],'reasons':reasons,'evidence':c['evidence'],'point_id':c.get('point_id')})
    unresolved={i['evidence_id'] for i in checks if i['code']=='UNRESOLVED_CONTINUATION_REFERENCE'}
    continuation_sources=[{'id':c['id'],'sheet':sheets.get(c['sheet_id'],{}).get('printed_id') or c['sheet_id'],
        'source':c['source_text'],'target_sheet':c.get('target_printed_sheet'),'target_line':c.get('target_line_proposal'),
        'state':'PROPOSED — SOURCE REVIEW REQUIRED' if c['id'] in unresolved else 'SHARED IDENTITY REVIEWED','source_sha':c['source_sha256']}
        for c in project.get('automation',{}).get('continuation_candidates',[])]
    from packages.physical.cod import proposals as cod_proposals
    bends=[]
    for c in cod_proposals(project):
        cod_coordinates=c.get('coordinates_mm') or {}
        bends.append({'id':c['component_id'],'component_id':c['component_id'],'node':nodes.get(c['point_id'],{}).get('number'),
            'state':c['status'],'x':cod_coordinates.get('X'),'y':cod_coordinates.get('Y'),'z':cod_coordinates.get('Z'),
            'station':None,'radius':None,'legs':', '.join(str(nodes.get(v,{}).get('number')) for v in c.get('leg_point_ids',[]))})
    return [
        table('Bend COD',[('node','COD node','number'),('state','Reconstruction state','text'),('x','Proved X / East (mm)','decimal'),('y','Proved Y / North (mm)','decimal'),('z','Proved Z / Up (mm)','decimal'),('station','Station inferred from COD (mm)','decimal'),('radius','Bend radius inferred (mm)','decimal'),('legs','Engineering leg nodes','text'),('component_id','Elbow occurrence ID','text')],bends),
        table('Continuations',[('line','Full line ID','text'),('left','Source node','number'),('right','Other depiction node','number'),('shared','Shared node','number'),('axis','Engineering axis','text'),('left_coordinate','Original source coordinate (mm)','decimal'),('right_coordinate','Other source coordinate (mm)','decimal'),('delta','Other minus source (mm)','decimal'),('state','Match state','text'),('reasons','Current reasons','text'),('evidence','Engineering evidence','text'),('point_id','Shared physical ID','text'),('continuation_id','Review ID','text')],continuations),
        table('Continuation sources',[('sheet','Source sheet','text'),('source','Printed continuation reference','text'),('target_sheet','Referenced sheet number','number'),('target_line','Referenced full line proposal','text'),('state','Review state','text'),('source_sha','Source PDF SHA256','text'),('id','Source observation ID','text')],continuation_sources),
        table('Component ports', [('item','Item','text'),('occurrence','Occurrence','number'),('line','Full line ID','text'),('kind','Component type','text'),('port','Required physical interface','text'),('node','Node','number'),('station','Accepted station (mm)','decimal'),('state','Association state','text'),('reasons','Unresolved reasons','text'),('proof_kind','Source feature','text'),('evidence','Source evidence','text'),('point_id','Physical point ID','text'),('component_id','Component ID','text'),('review_label','Temporary review point','text'),('location_state','Source location status','text'),('source_sha','Source PDF SHA256','text'),('source_bbox','Source evidence box (PDF points only)','text'),('exception_ids','Exception IDs','text')],ports),
        table('Dimensions',[('kind','Constraint type','text'),('axis','Signed engineering axis','text'),('from_node','From / coordinate node','number'),('to_node','To node','number'),('source_text','Original source dimension','text'),('value','Canonical value (mm)','decimal'),('tolerance','Declared tolerance (mm)','decimal'),('state','Review state','text'),('sheet','Source sheet','text'),('evidence','Engineering evidence','text'),('source_sha','Original PDF SHA256','text'),('id','Constraint ID','text')],dimensions),
        table('Coordinates',[('node','Node','number'),('line','Full line ID','text'),('axis','Engineering axis','text'),('coordinate','Source coordinate (mm)','decimal'),('relative','Relative to basis (mm)','decimal'),('basis','Relative basis node','number'),('state','Constraint status','text'),('tolerance','Declared uncertainty (mm)','decimal'),('evidence_group','Evidence group','text'),('point_id','Physical point ID','text')],coordinates),
    ]
