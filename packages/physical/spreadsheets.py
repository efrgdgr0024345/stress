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
            codes=sorted({i['code'] for i in state['issues'] if i.get('component_id')==c['id']})
            ports.append({'id':c['id']+':'+key,'component_id':c['id'],'material_id':c['material_id'],
                'item':c['item_no'],'occurrence':c['occurrence'],'line':c['line_id'],'kind':c['kind'],
                'port':key,'node':n.get('number') if n else None,'point_id':n['id'] if n else None,
                'station':n.get('station_mm') if n else None,'state':'REVIEW REQUIRED' if codes else 'SOURCE ASSOCIATION REVIEWED',
                'reasons':', '.join(codes),'evidence':proof.get('evidence'),'proof_kind':proof.get('kind'),
                'sheet_id':proof.get('sheet_id') or c['sheet_id']})
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
    return [
        table('Component ports', [('item','Item','text'),('occurrence','Occurrence','number'),('line','Full line ID','text'),('kind','Component type','text'),('port','Required physical interface','text'),('node','Node','number'),('station','Accepted station (mm)','decimal'),('state','Association state','text'),('reasons','Unresolved reasons','text'),('proof_kind','Source feature','text'),('evidence','Source evidence','text'),('point_id','Physical point ID','text'),('component_id','Component ID','text')],ports),
        table('Dimensions',[('kind','Constraint type','text'),('axis','Signed engineering axis','text'),('from_node','From / coordinate node','number'),('to_node','To node','number'),('source_text','Original source dimension','text'),('value','Canonical value (mm)','decimal'),('tolerance','Declared tolerance (mm)','decimal'),('state','Review state','text'),('sheet','Source sheet','text'),('evidence','Engineering evidence','text'),('source_sha','Original PDF SHA256','text'),('id','Constraint ID','text')],dimensions),
        table('Coordinates',[('node','Node','number'),('line','Full line ID','text'),('axis','Engineering axis','text'),('coordinate','Source coordinate (mm)','decimal'),('relative','Relative to basis (mm)','decimal'),('basis','Relative basis node','number'),('state','Constraint status','text'),('tolerance','Declared uncertainty (mm)','decimal'),('evidence_group','Evidence group','text'),('point_id','Physical point ID','text')],coordinates),
    ]
