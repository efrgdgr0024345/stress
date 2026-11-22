"""Component ports represent physical interfaces, never drawing-pixel lengths.

Inventory creates bounded, unlocated requirements. Only an evidenced connection
may associate a requirement with an existing physical point. Shared interfaces
reuse point UUIDs; multiple labels remain sheet instances of that same point.
"""
from copy import deepcopy
import hashlib
import json
from decimal import Decimal
import re
from uuid import uuid5,NAMESPACE_URL

SCHEMA='physical-ports-1'
POLICIES={
    'flange':{'ports':('flange_face','opposite_pipe_dot'),'proof':('FLANGE_FACE','BLACK_DOT'),'reason':'UNKNOWN_FLANGE_END'},
    'valve':{'ports':('process_in','process_out'),'proof':('PROCESS_CONNECTION','PROCESS_CONNECTION'),'reason':'UNKNOWN_VALVE_END'},
    'inline_instrument':{'ports':('process_in','process_out'),'proof':('PROCESS_CONNECTION','PROCESS_CONNECTION'),'reason':'UNKNOWN_INSTRUMENT_STATION'},
    'single_instrument':{'ports':('process_connection',),'proof':('PROCESS_CONNECTION',),'reason':'UNKNOWN_INSTRUMENT_STATION'},
    'instrument_unclassified':{'ports':(),'proof':(),'reason':'INSTRUMENT_CONNECTION_TYPE_UNCONFIRMED'},
    'tee':{'ports':('centreline_intersection',),'proof':('CENTRELINE_INTERSECTION',),'reason':'TEE_INTERSECTION_UNCONFIRMED'},
    'elbow':{'ports':('theoretical_cod',),'proof':('DIMENSION_CHAIN_COD',),'reason':'UNCONFIRMED_ELBOW_COD'},
    'support':{'ports':('support_station',),'proof':('SUPPORT_STATION',),'reason':'UNKNOWN_SUPPORT_STATION'},
}
MAX_OCCURRENCES=1000


def identity(*parts):return str(uuid5(NAMESPACE_URL,':'.join(str(v) for v in parts)))


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def component_kind(material):
    family=material['family'];text=material.get('description','').upper()
    if family=='instrument':
        if re.search(r'\bPIT\b',text):return 'single_instrument'
        if re.search(r'\b(?:FLOW\s*METER|FLOWMETER|INLINE|IN-LINE)\b',text):return 'inline_instrument'
        return 'instrument_unclassified'
    return family if family in POLICIES else None


def requirements(project):
    """Idempotent desired occurrences, preserving explicit reviewed mappings."""
    existing={c['id']:c for c in project.get('physical_model',{}).get('components',[])}
    components=[];issues=[];retired=[]
    for material in project['materials']:
        kind=component_kind(material)
        if kind is None:
            if re.search(r'\b(?:REDUCER|EXPANSION\s+JOINT|ORIFICE|STRAINER|FILTER|CAP)\b',material.get('description',''),re.I):
                issues.append({'code':'UNSUPPORTED_COMPONENT_RULE','material_id':material['id'],'message':f"Item {material['item_no']}: this component needs an explicit supported physical-connection rule; no station was invented."})
            continue
        if kind=='valve' and re.search(r'\bDBB\b|DOUBLE\s+BLOCK',material.get('description',''),re.I):
            issues.append({'code':'DBB_AUXILIARY_CONNECTION_REVIEW','material_id':material['id'],'message':f"Item {material['item_no']}: confirm any documented bleed/drain connections independently; two main process ports do not establish their stations."})
        quantity=material.get('quantity')
        if material.get('quantity_unit','count')!='count' or quantity is None:
            issues.append({'code':'COMPONENT_QUANTITY_UNRESOLVED','material_id':material['id'],
                           'message':f"Item {material['item_no']}: a confirmed component count is needed before preparing its physical interfaces."})
            continue
        if not isinstance(quantity,int) or isinstance(quantity,bool) or quantity<0:
            issues.append({'code':'COMPONENT_QUANTITY_UNRESOLVED','material_id':material['id'],'message':f"Item {material['item_no']}: an integral nonnegative component count is required."});continue
        if len(components)+quantity>MAX_OCCURRENCES:
            issues.append({'code':'COMPONENT_OCCURRENCE_LIMIT','material_id':material['id'],
                           'message':f"Item {material['item_no']}: {quantity} occurrences exceed this bounded {MAX_OCCURRENCES}-component model. Source quantities are retained; this model remains incomplete."})
            continue
        for occurrence in range(1,quantity+1):
            uid=identity(project['id'],'material-occurrence',material['id'],occurrence)
            old=existing.get(uid)
            source=fingerprint({k:material.get(k) for k in ('family','description','size','sheet_id')})
            if old and old.get('family')==material['family']:
                component=deepcopy(old)
                if component.get('classification_source')!=source:
                    component['verification']='proposed'
                    if component['kind']!=kind:
                        retired.append(deepcopy(old));component.update(kind=kind,ports={key:None for key in POLICIES[kind]['ports']})
            else:
                if old:retired.append(deepcopy(old))
                component={'id':uid,'material_id':material['id'],'family':material['family'],
                           'kind':kind,'occurrence':occurrence,'verification':'proposed','evidence':'',
                           'ports':{key:None for key in POLICIES[kind]['ports']}}
            component.update(classification_source=source,sheet_id=material['sheet_id'],item_no=material['item_no'],
                             line_id=next((s['line_id'] for s in project['sheets'] if s['id']==material['sheet_id']),project['line_id']))
            components.append(component)
    active={c['id'] for c in components}
    retired.extend(deepcopy(c) for c in existing.values() if c['id'] not in active)
    return components,issues,retired


def prepare(project):
    components,issues,retired=requirements(project)
    model=project.setdefault('physical_model',{'schema':SCHEMA,'constraints':[],'components':[]})
    if retired:
        archive=model.setdefault('retired_components',[])
        known={fingerprint(c) for c in archive}
        archive.extend(c for c in retired if fingerprint(c) not in known)
    model.update(schema=SCHEMA,components=components,preparation_issues=issues)
    roles={n['id']:[] for n in project['nodes']}
    for component in components:
        for key,port in component['ports'].items():
            if port and port.get('point_id') in roles:
                roles[port['point_id']].append({'component_id':component['id'],'kind':component['kind'],'port':key})
    for node in project['nodes']:
        if roles[node['id']]:node['component_ports']=roles[node['id']]
        else:node.pop('component_ports',None)
    found=audit(project)['issues']
    for node in project['nodes']:
        reasons=sorted({i['code'] for i in found if i.get('point_id')==node['id']})
        if reasons:node['component_review_reasons']=reasons
        else:node.pop('component_review_reasons',None)
    return model


def audit(project):
    components,issues,_=requirements(project)
    nodes={n['id']:n for n in project['nodes']};sheets={s['id']:s for s in project['sheets']}
    associations={n:[] for n in nodes}
    for component in components:
        policy=POLICIES[component['kind']]
        def issue(code,message,point=None):
            issues.append({'code':code,'component_id':component['id'],'material_id':component['material_id'],
                'sheet_id':component['sheet_id'],'point_id':point,'message':f"Item {component['item_no']} / occurrence {component['occurrence']}: {message}"})
        if not policy['ports']:issue(policy['reason'],'confirm whether this instrument has one or two physical process connections.')
        mapped=[]
        for key,proof_kind in zip(policy['ports'],policy['proof']):
            port=component.get('ports',{}).get(key);node=nodes.get(port.get('point_id')) if port else None
            if not node:
                issue(policy['reason'],f'{key.replace("_"," ")} is unlocated; no physical point has been fabricated.');continue
            mapped.append(node['id']);associations[node['id']].append({'component_id':component['id'],'kind':component['kind'],'port':key})
            proof=port.get('proof',{});sheet=sheets.get(proof.get('sheet_id'))
            box=proof.get('bbox',[])
            instance=next((i for i in node.get('instances',[]) if i['sheet_id']==proof.get('sheet_id')),None)
            anchor_current=bool(instance and len(box)==4 and box[0]<=instance['anchor'][0]<=box[2] and box[1]<=instance['anchor'][1]<=box[3])
            source_current=bool(sheet and (proof.get('content_hash')==sheet.get('content_hash') if sheet.get('content_hash') else proof.get('source_sha256')==sheet.get('sha256')))
            if (not source_current or proof.get('kind')!=proof_kind or
                component.get('verification')!='reviewed' or not proof.get('evidence') or not anchor_current):
                issue(policy['reason'],f'{key.replace("_"," ")} requires current source association proof.',node['id'])
            if node['line_id']!=component['line_id']:issue('COMPONENT_LINE_MISMATCH','a mapped point belongs to a different full line ID.',node['id'])
            if node.get('station_mm') is None or not node.get('evidence') or node.get('verification')=='proposed':
                issue(policy['reason'],'physical station evidence is still unresolved.',node['id'])
            if component['kind']=='tee' and (node['kind']!='tee' or node['route']!='main'):
                issue('TEE_INTERSECTION_UNCONFIRMED','the common tee point must belong to the main-run series.',node['id'])
            if component['kind']=='elbow' and not proof.get('dimension_convention'):
                issue('UNCONFIRMED_ELBOW_COD','state the engineering dimension convention proving theoretical COD; page bends and pixel proportions are insufficient.',node['id'])
        if len(mapped)==2:
            a,b=(nodes[v] for v in mapped)
            if a['id']==b['id'] or (a['route']==b['route'] and a.get('station_mm') is not None and b.get('station_mm') is not None and Decimal(a['station_mm'])==Decimal(b['station_mm'])):
                issue('COMPONENT_ENDS_COINCIDENT','opposite process ends must be distinct physical stations; both cannot be placed at one flange face.',a['id'])
    return {'schema':SCHEMA,'components':components,'associations':associations,
            'issues':[dict(i,severity='critical') for i in issues]}


def is_support(node):
    return node.get('kind')=='support' or any(p['kind']=='support' for p in node.get('component_ports',[]))
