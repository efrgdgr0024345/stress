"""Current UUID graph and retained numbering events shared by web/XLSX/CSV."""
from decimal import Decimal,localcontext
from packages.engineering.graph_review import audit_graph
from packages.physical.constraints import solve
from packages.physical.source_review import point_label
from packages.physical.stations import station_pair_comparable


def tables(project):
    nodes={n['id']:n for n in project['nodes']};report=audit_graph(project)
    solved={(e['from'],e['to']):e for e in solve(project)['elements']}
    def table(name,columns,rows):
        return {'name':name,'columns':[{'key':k,'label':label,'kind':kind} for k,label,kind in columns],'rows':rows}
    edges=[]
    for edge in report['graph']['edges']:
        a,b=nodes[edge['from']],nodes[edge['to']];solution=solved.get((a['id'],b['id']),{})
        with localcontext() as context:
            context.prec=200
            distance=str(abs(Decimal(b['station_mm'])-Decimal(a['station_mm']))) if station_pair_comparable(a,b) else None
        edges.append({'id':a['id']+':'+b['id'],'from_point_id':a['id'],'to_point_id':b['id'],
            'from_label':point_label(a),'to_label':point_label(b),'line_id':edge['line_id'],'route':edge['route'],
            'dx':solution.get('delta_mm',{}).get('X'),'dy':solution.get('delta_mm',{}).get('Y'),
            'dz':solution.get('delta_mm',{}).get('Z'),'station_distance':distance,
            'source_pages':', '.join(sorted({i['sheet_id'] for n in (a,b) for i in n.get('instances',[])})),
            'evidence_groups':str(solution.get('evidence_groups',{}))})
    mapping=[{**v,'id':v['point_id'],'canonical_point_id':v['point_id'],
              'point_label':point_label(nodes[v['point_id']]) if v['point_id'] in nodes else None,
              'state':nodes.get(v['point_id'],{}).get('topology_state','ASSIGNED')} for v in project.get('numbering_map',[])]
    latest=(project.get('numbering_history') or [{}])[-1]
    mapping.extend({'id':v['retired_point_id'],'point_id':v['retired_point_id'],
                    'canonical_point_id':v['physical_point_id'],'old':v['old'],'new':v['new'],
                    'state':'RETIRED_ALIAS','point_label':point_label(nodes[v['physical_point_id']]) if v['physical_point_id'] in nodes else None}
                   for v in latest.get('alias_rows',[]))
    history=[{'id':r['sha256'],'revision':r['revision'],'action':r['action'],'reviewed_by':r.get('reviewed_by'),
              'reviewed_at':r.get('reviewed_at'),'points':len(r['mapping']),
              'changed':sum(v['old']!=v['new'] for v in r['mapping']),
              'aliases':len(r.get('alias_rows',[])),'sha256':r['sha256']}
             for r in project.get('numbering_history',[])]
    return [
        table('Graph edges',[
            ('from_label','From point','text'),('to_label','To point','text'),('line_id','Full line ID','text'),('route','Route','text'),
            ('dx','Source-constrained DX (mm)','decimal'),('dy','Source-constrained DY (mm)','decimal'),
            ('dz','Source-constrained DZ (mm)','decimal'),('station_distance','Comparable route span (mm)','decimal'),
            ('from_point_id','From physical point ID','text'),('to_point_id','To physical point ID','text'),
            ('source_pages','Source sheet IDs','text'),('evidence_groups','Coordinate evidence groups','text')],edges),
        table('Numbering map',[
            ('point_label','Review point / canonical node','text'),('old','Previous CAESAR number','number'),
            ('new','Current CAESAR number','number'),('state','Physical identity state','text'),
            ('point_id','Original physical point ID','text'),('canonical_point_id','Current physical point ID','text')],mapping),
        table('Numbering history',[
            ('revision','Project revision','number'),('action','Numbering action','text'),('points','Current physical points','number'),
            ('changed','Changed numbers','number'),('aliases','Retained identity aliases','number'),
            ('reviewed_by','Recorded by','text'),('reviewed_at','Recorded at','text'),('sha256','Complete numbering event SHA256','text')],history),
    ]
