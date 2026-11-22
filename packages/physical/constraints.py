"""Signed engineering-coordinate constraints, independent of PDF/view geometry.

Each axis is solved separately. Unknown offsets stay unknown, inconsistent
connected systems are not averaged, and original source text/proof is retained.
"""
from collections import deque
from decimal import Decimal,localcontext
import hashlib
import json
from packages.engineering import dimension_mm,topology

AXES=('X','Y','Z')
MAX_POINTS=2000
MAX_CONSTRAINTS=6000


def observations(project,invalid=None):
    invalid=invalid if invalid is not None else []
    sheets={s['id']:s for s in project.get('sheets',[])};result=[]
    for c in project.get('physical_model',{}).get('constraints',[]):
        sheet=sheets.get(c.get('sheet_id'))
        if c.get('verification')!='reviewed':
            invalid.append({'code':'DIMENSION_PROPOSAL_REVIEW','constraint_id':c['id'],'message':'A source dimension proposal requires explicit review.'});continue
        if c.get('sheet_id') and (not sheet or c.get('source_content_hash')!=sheet.get('content_hash')):
            invalid.append({'code':'DIMENSION_SOURCE_STALE','constraint_id':c['id'],'message':'A source dimension refers to a changed or retired drawing page.'});continue
        result.append(dict(c))
    for element in project.get('analysis_model',{}).get('elements',[]):
        if element.get('geometry_origin')=='constraint-solution':
            result.extend(dict(v) for v in element.get('geometry_source_inputs',[]));continue
        if not element.get('evidence') or element.get('verification') not in ('engineer-entered','reviewed'):continue
        for axis in AXES:
            value=element.get('d'+axis.lower()+'_mm')
            if value is not None:
                result.append({'id':element['id']+':'+axis,'kind':'DELTA','axis':axis,
                    'from_point_id':element['from_point_id'],'to_point_id':element['to_point_id'],
                    'value_mm':value,'source_text':value+' mm','tolerance_mm':'0',
                    'evidence':element['evidence'],'verification':'reviewed','source':'analysis-element'})
    return result


def solve(project):
    nodes={n['id']:n for n in project['nodes']};issues=[];inputs=sorted(observations(project,issues),key=lambda v:v['id'])
    output={n:{'point_id':n,'axes':{}} for n in nodes};groups={}
    source_sha=hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    for element in project.get('analysis_model',{}).get('elements',[]):
        if element.get('geometry_origin')=='constraint-solution' and element.get('geometry_source_sha256')!=source_sha:
            issues.append({'code':'DIMENSION_SOLUTION_STALE','element_id':element['id'],'message':'Element XYZ values were accepted from an earlier constraint set. Review and accept the current solution before modelling.'})
    if len(nodes)>MAX_POINTS or len(inputs)>MAX_CONSTRAINTS:
        return {'schema':'signed-xyz-1','coordinates':[],'elements':[],'inputs':[],
            'evidence_groups':{},'issues':[{'code':'DIMENSION_SOLVER_LIMIT','severity':'critical',
            'message':'This model exceeds the bounded coordinate solver. No partial coordinates have been accepted.'}],
            'physical_stations_modified':False,'drawing_pixels_used':False,'input_sha256':source_sha}
    with localcontext() as context:
        context.prec=50
        for axis in AXES:
            graph={n:[] for n in nodes};anchors={n:[] for n in nodes}
            for c in inputs:
                if c['axis']!=axis:continue
                a=c.get('from_point_id');b=c.get('to_point_id')
                if a not in nodes or c['kind']=='DELTA' and b not in nodes:
                    issues.append({'code':'DIMENSION_POINT_RETIRED','constraint_id':c['id'],'message':'A dimensional constraint refers to a retired physical point.'});continue
                value=Decimal(c['value_mm']);tolerance=Decimal(c.get('tolerance_mm','0'))
                if not value.is_finite() or not tolerance.is_finite() or tolerance<0:raise ValueError('Invalid canonical dimension constraint.')
                if c['kind']=='COORDINATE':anchors[a].append((value,tolerance,c['id']))
                else:
                    graph[a].append((b,value,tolerance,c['id']));graph[b].append((a,-value,tolerance,c['id']))
            visited=set()
            for start in nodes:
                if start in visited:continue
                queue=deque([start]);potential={start:Decimal(0)};uncertainty={start:Decimal(0)};proof=set();conflicts=[]
                while queue:
                    a=queue.popleft();visited.add(a)
                    for b,delta,tolerance,cid in graph[a]:
                        proof.add(cid)
                        value=potential[a]+delta;limit=uncertainty[a]+tolerance
                        if b not in potential:
                            potential[b]=value;uncertainty[b]=limit;queue.append(b)
                        elif abs(potential[b]-value)>uncertainty[b]+limit:
                            conflicts.append({'constraint_id':cid,'point_id':b,'residual_mm':str(potential[b]-value)})
                offsets=[]
                for point,relative in potential.items():
                    offsets.extend((value-relative,tolerance+uncertainty[point],cid) for value,tolerance,cid in anchors[point])
                offset=offsets[0][0] if offsets else None
                for value,tolerance,cid in offsets[1:]:
                    if abs(value-offset)>tolerance+offsets[0][1]:conflicts.append({'constraint_id':cid,'residual_mm':str(value-offset)})
                all_proof=sorted(proof|{v[2] for v in offsets});group=axis+':'+start
                groups[group]={'constraint_ids':all_proof,'points':list(potential),'axis':axis}
                for point,value in potential.items():
                    output[point]['axes'][axis]={'value_mm':str(value+offset) if offset is not None and not conflicts else None,
                        'relative_mm':str(value) if not conflicts and (graph[point] or offsets) else None,'relative_basis_point_id':start,
                        'status':'CONFLICT' if conflicts else 'SOLVED' if offset is not None else 'RELATIVE_ONLY' if graph[point] else 'UNKNOWN',
                        'tolerance_mm':str(uncertainty[point]+(offsets[0][1] if offsets else 0)) if graph[point] or offsets else None,
                        'evidence_group':group}
                if conflicts:issues.append({'code':'COORDINATE_MISMATCH','axis':axis,'point_ids':list(potential),
                    'evidence_ids':all_proof,'conflicts':conflicts,'message':f'{axis}: signed dimensional constraints conflict. No conflicting coordinates were accepted or averaged.'})
        deltas=[]
        for edge in topology(project['nodes'])['edges']:
            a,b=edge['from'],edge['to'];row={**edge,'delta_mm':{},'evidence_groups':{}}
            for axis in AXES:
                first=output[a]['axes'][axis];second=output[b]['axes'][axis]
                same=first['relative_basis_point_id']==second['relative_basis_point_id']
                known=same and first['relative_mm'] is not None and second['relative_mm'] is not None
                row['delta_mm'][axis]=str(Decimal(second['relative_mm'])-Decimal(first['relative_mm'])) if known else None
                row['evidence_groups'][axis]=[first['evidence_group']] if known else []
            first_node,second_node=nodes[a],nodes[b]
            bends=any(n['kind']=='elbow' or any(p['kind']=='elbow' for p in n.get('component_ports',[])) for n in (first_node,second_node))
            if (not bends and first_node['route']==second_node['route'] and
                all(v is not None for v in row['delta_mm'].values()) and
                all(n.get('station_mm') is not None and n.get('evidence') for n in (first_node,second_node))):
                length=sum(Decimal(v)**2 for v in row['delta_mm'].values()).sqrt()
                gap=abs(Decimal(second_node['station_mm'])-Decimal(first_node['station_mm']))
                if abs(length-gap)>Decimal('.01'):
                    issues.append({'code':'STATION_GEOMETRY_MISMATCH','point_ids':[a,b],
                        'message':'Signed XYZ segment length disagrees with accepted along-route stations. Review the centreline/bend convention; neither source value was overwritten.',
                        'coordinate_length_mm':str(length),'station_gap_mm':str(gap)})
            deltas.append(row)
    return {'schema':'signed-xyz-1','axes':{'X':'East / model X','Y':'North / model Y','Z':'Elevation / model Z'},
            'coordinates':list(output.values()),'elements':deltas,'inputs':inputs,'evidence_groups':groups,
            'issues':[dict(i,severity='critical') for i in issues],
            'physical_stations_modified':False,'drawing_pixels_used':False,'input_sha256':source_sha}
