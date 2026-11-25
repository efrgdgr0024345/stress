"""Explicit CAESAR15.1 auxiliary inputs, never engineering or import qualification.

BEND generation deliberately remains blocked: the official field-count and
theoretical-COD/native far-end geometry contracts have not been independently
resolved. Complete documented rigid/tee/basic-restraint records are candidates.
"""
from copy import deepcopy
from decimal import Decimal,InvalidOperation,localcontext
import hashlib
import json

from packages.automation.recognize import identity
from packages.engineering import topology,topology_assigned,source_observations,source_location_reviewed
from packages.physical import requirements

SCHEMA='cii-components-15.1-v1'
MAX_RECORDS=2000
B31J_CODES={43,53,63}
RESTRAINT_TYPES={2,3,4,13,14,15,16,17,18}
SIF_FIELDS=('in_plane_sif','out_plane_sif','axial_sif','torsion_sif','pressure_sif')
INDEX_FIELDS=('in_plane_index','out_plane_index','axial_index','torsion_index','pressure_index')


def _field(key,label,kind='decimal',unit=None,options=None,required=True):
    return {'key':key,'label':label,'type':kind,'unit':unit,'options':options or [],'required':required}


FIELD_SCHEMA={
    'RIGID':[_field('weight_n','Actual component total weight','decimal','N'),
        _field('rigid_type','Rigid component type','enum',options=['1','2']),
        _field('weight_scope','Weight scope','enum',options=['COMPONENT_TOTAL_EXCLUDES_FLUID_INSULATION'])],
    'TEE':[_field('tee_type','B31J Welding Tee type','enum',options=['3'])]+
        [_field(k,k.replace('_',' ').title(),'decimal','dimensionless') for k in SIF_FIELDS+INDEX_FIELDS]+
        [_field('code_note_1','Code note option 1','enum',options=['UNSPECIFIED','SELECTED','CLEARED']),
         _field('code_note_2','Code note option 2','enum',options=['UNSPECIFIED','SELECTED','CLEARED']),
         _field('no_geometry_overrides','Standard welding tee; no geometric/code overrides','bool')],
    'RESTRAINT':[_field('type_code','Global target restraint type','enum',options=[str(v) for v in sorted(RESTRAINT_TYPES)]),
        _field('axis_basis','Direction basis','enum',options=['TARGET_CAESAR_AXES']),
        _field('grounded','Connected to ground, no CNode','bool'),
        _field('stiffness_n_per_mm','Translational stiffness','decimal','N/mm'),
        _field('gap_mm','Explicit translational gap','decimal','mm'),
        _field('friction_coefficient','Explicit friction coefficient','decimal','dimensionless'),
        _field('support_tag','Support tag','text'),_field('support_guid','Support GUID','text',required=False)],
    'BEND':[_field('radius_mm','Source bend radius','decimal','mm'),
        _field('native_to_point_id','Independently reviewed native far-end point','point'),
        _field('representation_note','COD versus native representation evidence','text'),
        _field('vendor_geometry_reference','Verified15.1 native geometry contract reference','text'),
        _field('vendor_field_layout_reference','Verified15.1 BEND field-layout reference','text')]
}


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def records(project):return project.get('analysis_model',{}).get('native_components',[])


def _edge_rows(project):
    return [{**edge,'id':identity(project['id'],edge['from'],edge['to']),
        'from_point_id':edge['from'],'to_point_id':edge['to']} for edge in topology(project['nodes'])['edges']]


def _context(project,record):
    by_id={n['id']:n for n in project['nodes']};edge=next((e for e in _edge_rows(project) if e['id']==record.get('element_id')),None)
    component=next((c for c in requirements(project)[0] if c['id']==record.get('component_id')),None)
    material=next((m for m in project.get('materials',[]) if component and m['id']==component['material_id']),None)
    ids={record.get('point_id')}
    if edge:ids.update((edge['from'],edge['to']))
    if component:ids.update(v['point_id'] for v in component['ports'].values() if v)
    # Main-run tee validation depends on every explicit adjacent leg.
    if record['kind']=='TEE' and record.get('point_id'):
        for e in _edge_rows(project):
            if record['point_id'] in (e['from'],e['to']):ids.update((e['from'],e['to']))
    sheets={s['id']:s for s in project.get('sheets',[])};points=[]
    for uid in sorted(i for i in ids if i in by_id):
        node=by_id[uid]
        points.append({**{k:deepcopy(node.get(k)) for k in ('id','line_id','route','order','kind','takeoff_id','topology_state','station_mm','coordinates_mm','station_proof','manual_station_basis','topology_proof')},
            'source_observations':deepcopy(source_observations(node)),
            'instances':[{'sheet_id':i['sheet_id'],'anchor':deepcopy(i['anchor']),
                'source':{k:deepcopy(sheets.get(i['sheet_id'],{}).get(k)) for k in ('sha256','content_hash','line_id','printed_id','identity_verified')}} for i in node.get('instances',[])]})
    element_ids={record.get('element_id')}
    if record['kind']=='TEE':element_ids.update(e['id'] for e in _edge_rows(project) if record.get('point_id') in (e['from'],e['to']))
    return {'kind':record['kind'],'component':component,'points':points,'edge':edge,
        'material':{k:deepcopy(material.get(k)) for k in ('id','family','description','size','source_sha256',
            'catalog_match','project_manufacturer_status')} if material else None,
        'elements':[deepcopy(e) for e in project.get('analysis_model',{}).get('elements',[]) if e['id'] in element_ids],
        'source_sheet':{k:deepcopy(sheets.get(record.get('source_sheet_id'),{}).get(k)) for k in ('id','sha256','content_hash','line_id','printed_id','identity_verified')},
        'settings':{k:project.get('analysis_model',{}).get(k) for k in ('piping_code_id','vertical_axis','origin_point_id','local_origin_confirmed')},
        'values':record.get('values',{}),'point_id':record.get('point_id'),'component_id':record.get('component_id'),
        'review_state':record.get('review_state'),'evidence':record.get('evidence')}


def _issue(code,message,record=None,**extra):
    return {'code':code,'message':message,'severity':'critical','color':'blue',
        'record_id':record.get('id') if record else None,'component_id':record.get('component_id') if record else None,
        'point_id':record.get('point_id') if record else None,'element_id':record.get('element_id') if record else None,
        'engineering_approved':False,**extra}


def _number(values,key,positive=False,maximum='1000000000000'):
    value=values.get(key)
    if value is None or value=='':raise ValueError(f'{key} is unknown; supply its explicit canonical value.')
    try:n=Decimal(str(value))
    except InvalidOperation:raise ValueError(f'{key} must be a finite canonical decimal.') from None
    if not n.is_finite() or n<0 or positive and n<=0 or n>Decimal(maximum):raise ValueError(f'{key} is outside this explicit component profile.')
    return str(n)


def _integer(values,key,allowed):
    value=_number(values,key)
    if Decimal(value)!=int(Decimal(value)) or int(Decimal(value)) not in allowed:raise ValueError(f'{key} is not supported by this documented minimum profile.')
    return int(Decimal(value))


def _text(value,key,required=False):
    if value is None:value=''
    if not isinstance(value,str) or len(value)>100 or any(ord(c)<32 for c in value):raise ValueError(f'{key} must fit the documented100-character literal text field.')
    try:value.encode('cp1252')
    except UnicodeEncodeError:raise ValueError(f'{key} must fit the native Windows-1252 field.') from None
    if required and not value.strip():raise ValueError(f'{key} requires an explicit source tag.')
    return value


def _compiled(project,record):
    values=record.get('values',{});kind=record['kind'];by_id={n['id']:n for n in project['nodes']}
    edge=next((e for e in _edge_rows(project) if e['id']==record.get('element_id')),None)
    point=by_id.get(record.get('point_id'));component=next((c for c in requirements(project)[0] if c['id']==record.get('component_id')),None)
    if kind=='BEND':
        return None,[_issue('BEND_NATIVE_GEOMETRY_CONTRACT_UNVERIFIED','Physical theoretical COD is not a CAESAR far-end bend node. A verified15.1 native geometry contract/sample is required; no bridge/delta/node was guessed.',record),
            _issue('BEND_NEUTRAL_FIELD_LAYOUT_AMBIGUOUS','Official15.1 BEND states15array members/13used but lists14 fields. Native bend serialization remains blocked pending authoritative contract verification.',record)]
    issues=[]
    if not edge:issues.append(_issue('NATIVE_ELEMENT_REQUIRED','Select a current explicitly ordered physical model element.',record))
    if kind in ('TEE','RESTRAINT') and (not point or not topology_assigned(point)):
        issues.append(_issue('NATIVE_POINT_REQUIRED','Select an active explicitly assigned physical point; unknown source locations cannot become native nodes.',record))
    if edge and point and kind in ('TEE','RESTRAINT') and point['id'] not in (edge['from'],edge['to']):
        issues.append(_issue('NATIVE_CARRIER_POINT_MISMATCH','The auxiliary carrier element must touch its declared physical node.',record))
    if component:
        expected={'TEE':'tee','RESTRAINT':'support'}.get(kind)
        if expected and component['kind']!=expected:
            issues.append(_issue('NATIVE_COMPONENT_KIND_MISMATCH','This native auxiliary cannot replace a different source component kind.',record))
        ports={v['point_id'] for v in component['ports'].values() if v}
        if kind=='RIGID' and (not edge or ports!={edge['from'],edge['to']}):issues.append(_issue('RIGID_INTERFACE_MAPPING_REQUIRED','Rigid endpoints must be the two reviewed physical ports of this component.',record))
        if kind in ('TEE','RESTRAINT') and (not point or point['id'] not in ports):issues.append(_issue('NATIVE_COMPONENT_POINT_MISMATCH','The selected node is not this component’s reviewed physical interface.',record))
    if issues:return None,issues
    data={k:record.get(k) for k in ('id','element_id','component_id','point_id')}
    if point:data['node_number']=point.get('number')
    try:
        if kind=='RIGID':
            data.update(weight_n=_number(values,'weight_n',True),rigid_type=_integer(values,'rigid_type',{1,2}))
            if values.get('weight_scope')!='COMPONENT_TOTAL_EXCLUDES_FLUID_INSULATION':raise ValueError('Confirm complete component total force weight, excluding fluid/insulation; unknown/body-only weight cannot become a rigid total.')
            if component and component['kind']!=('valve' if data['rigid_type']==1 else 'flange'):raise ValueError('The rigid type must match the classified source valve/flange.')
            data['point_ids']=[edge['from'],edge['to']]
        elif kind=='RESTRAINT':
            data.update(type_code=_integer(values,'type_code',RESTRAINT_TYPES),
                stiffness_n_per_mm=_number(values,'stiffness_n_per_mm',True),gap_mm=_number(values,'gap_mm'),
                friction_coefficient=_number(values,'friction_coefficient',maximum='10'))
            if values.get('axis_basis')!='TARGET_CAESAR_AXES' or values.get('grounded') is not True:
                raise ValueError('Confirm explicit target-CAESAR global axes and ground connection; angled/CNode/rotational/special restraints are not this minimum profile.')
            data.update(support_tag=_text(values.get('support_tag'),'support_tag',True),support_guid=_text(values.get('support_guid') or record['id'],'support_guid'))
        elif kind=='TEE':
            if project.get('analysis_model',{}).get('piping_code_id') not in B31J_CODES:raise ValueError('This welding-tee profile requires documented B31.3/B31J code43(2020),53(2022) or63(2024); code3 is2018without this B31J contract.')
            data['tee_type']=_integer(values,'tee_type',{3})
            if point['kind']!='tee' or point.get('route')!='main':raise ValueError('Use the existing common main-run tee UUID, never a duplicate branch tee.')
            if values.get('no_geometry_overrides') is not True:raise ValueError('Explicitly confirm the standard welding-tee/no-geometric-or-code-override profile; unsupported pad/taper/reinforcement data remain blocked.')
            for key in SIF_FIELDS+INDEX_FIELDS:
                data[key]=_number(values,key,True)
                if Decimal(data[key])<1:raise ValueError('This bounded welding-tee profile accepts explicit SIFs/indices of at least1; lower code-specific factors need a separately verified contract.')
            for key in ('code_note_1','code_note_2'):
                if values.get(key) not in ('UNSPECIFIED','SELECTED','CLEARED'):raise ValueError('Explicitly choose each documented code-note state; unspecified is the native9999.99 sentinel.')
                data[key]={'UNSPECIFIED':'9999.99','SELECTED':'1','CLEARED':'0'}[values[key]]
            adjacent=[e for e in _edge_rows(project) if point['id'] in (e['from'],e['to'])]
            mains=[e for e in adjacent if e['route']=='main'];branches=[e for e in adjacent if e['route']!='main']
            if len(adjacent)!=3 or len(mains)!=2 or len(branches)!=1 or edge['to']!=point['id'] or edge['route']!='main':
                raise ValueError('The minimum tee requires one incoming main carrier, one outgoing main leg and one explicit branch from the same main tee.')
            entered={e['id']:e for e in project.get('analysis_model',{}).get('elements',[])};vectors=[]
            for e in mains+branches:
                source=entered.get(e['id'],{})
                vector=[Decimal(source['d'+axis+'_mm']) for axis in ('x','y','z')]
                if e['to']==point['id']:vector=[v.copy_negate() for v in vector]
                vectors.append(vector)
            with localcontext() as context:
                context.prec=200
                a,b,c=vectors
                cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
                if not any(c) or any(not value.is_finite() for vector in vectors for value in vector) or any(cross) or sum(x*y for x,y in zip(a,b))>=0 or sum(x*y for x,y in zip(a,c))!=0:
                    raise ValueError('Accepted explicit vectors must prove opposed collinear main legs and an orthogonal standard-tee branch; no angle is inferred from the drawing.')
    except (ValueError,KeyError,TypeError,InvalidOperation) as error:
        return None,[_issue('NATIVE_COMPONENT_DATA_INCOMPLETE',str(error) or 'Required component data is unknown.',record)]
    return data,[]


def native_component_plan(project):
    components=requirements(project)[0];nodes={n['id']:n for n in project['nodes']};output={'rigids':[],'tees':[],'restraint_blocks':[],
        'bends':[],'issues':[],'supported_point_ids':[],'covered_component_ids':[],'qualified_application_roundtrip':False}
    current_records=[];ready=[]
    for record in records(project):
        current=bool(record.get('source_context_sha256')==digest(_context(project,record)) and record.get('reviewed_by') and record.get('reviewed_at'))
        compiled,issues=_compiled(project,record)
        if record.get('review_state')!='REVIEWED':issues.insert(0,_issue('NATIVE_COMPONENT_DRAFT','This native component input is a draft; missing values remain null and cannot be serialized.',record))
        if not current:issues.insert(0,_issue('NATIVE_COMPONENT_REVIEW_STALE','Source, topology, component mapping, explicit vectors/properties or native frame changed after this record; review again.',record))
        if issues:output['issues'].extend(issues)
        else:ready.append(compiled)
        current_records.append({**deepcopy(record),'current':current,'stale':not current,'ready':not issues,'issues':issues})
    used={};restraints={}
    for data in ready:
        record=next(r for r in records(project) if r['id']==data['id']);kind=record['kind'];key=(kind,data['element_id'])
        if kind!='RESTRAINT' and key in used:
            output['issues'].append(_issue('NATIVE_COMPONENT_DUPLICATE','Multiple records target one native auxiliary slot; no record was selected by array order.',record));continue
        used[key]=data['id']
        if kind=='RIGID':output['rigids'].append(data);output['supported_point_ids'].extend(data['point_ids'])
        elif kind=='TEE':output['tees'].append(data);output['supported_point_ids'].append(data['point_id'])
        elif kind=='RESTRAINT':restraints.setdefault(data['element_id'],[]).append(data);output['supported_point_ids'].append(data['point_id'])
        if data.get('component_id'):output['covered_component_ids'].append(data['component_id'])
    for element_id,entries in sorted(restraints.items()):
        if len(entries)>6:output['issues'].append(_issue('RESTRAINT_BLOCK_CAPACITY','At most six explicit restraints fit one documented carrier block; no extra record was omitted.'));continue
        output['restraint_blocks'].append({'element_id':element_id,'restraints':sorted(entries,key=lambda r:(r['point_id'],r['type_code'],r['id']))})
    requirements_rows=[];kind_map={'flange':'RIGID','valve':'RIGID','elbow':'BEND','tee':'TEE','support':'RESTRAINT'}
    for component in components:
        kind=kind_map.get(component['kind']);matches=[r for r in current_records if r.get('component_id')==component['id']]
        points=[v['point_id'] for v in component['ports'].values() if v]
        row={'id':'component:'+component['id'],'component_id':component['id'],'kind':kind or 'UNSUPPORTED',
            'material_id':component['material_id'],'sheet_id':component['sheet_id'],'point_id':points[0] if len(points)==1 else None,
            'point_ids':points,'item_no':component['item_no'],'occurrence':component['occurrence'],
            'missing':[] if component['id'] in output['covered_component_ids'] else ['NATIVE_COMPONENT_INPUT_REQUIRED'],
            'record':matches[-1] if matches else None}
        requirements_rows.append(row)
        if kind is None:output['issues'].append(_issue('NATIVE_COMPONENT_UNSUPPORTED','This component/auxiliary needs a separately documented representation; it cannot be silently omitted.',component_id=component['id']))
        elif component['id'] not in output['covered_component_ids'] and not matches:
            output['issues'].append(_issue('NATIVE_COMPONENT_INPUT_REQUIRED','Explicit current native '+kind+' data is required for this source component.',component_id=component['id']))
    for node in project['nodes']:
        kind=kind_map.get(node['kind'])
        if not kind or any(node['id'] in r['point_ids'] for r in requirements_rows):continue
        matches=[r for r in current_records if r.get('point_id')==node['id']]
        requirements_rows.append({'id':'point:'+node['id'],'component_id':None,'point_id':node['id'],'point_ids':[node['id']],
            'kind':kind,'sheet_id':next((i['sheet_id'] for i in node.get('instances',[])),None),
            'missing':[] if node['id'] in output['supported_point_ids'] else ['NATIVE_COMPONENT_INPUT_REQUIRED'],'record':matches[-1] if matches else None})
        if node['id'] not in output['supported_point_ids'] and not matches:
            output['issues'].append(_issue('NATIVE_COMPONENT_INPUT_REQUIRED','Explicit current native '+kind+' data is required for this physical node.',point_id=node['id']))
    output.update(records=current_records,requirements=requirements_rows)
    output['supported_point_ids']=sorted(set(output['supported_point_ids']));output['covered_component_ids']=sorted(set(output['covered_component_ids']))
    return output


def component_report(project):
    plan=native_component_plan(project)
    return {**plan,'schema':SCHEMA,'profile':'DOCUMENTED_RIGID_B31J_TEE_BASIC_TRANSLATIONAL_RESTRAINT_CANDIDATE',
        'field_schema':deepcopy(FIELD_SCHEMA),'elements':_edge_rows(project),
        'points':[{'id':n['id'],'point_id':n['id'],'number':n.get('number'),'label':str(n.get('number') or n.get('review_label') or n['id']),
            'kind':n['kind'],'line_id':n['line_id'],'route':n.get('route')} for n in project['nodes']],
        'native_generation_is_application_qualified':False,'engineering_approved':False}


def save_record(project,data,reviewer,reviewed_at,record_id=None):
    if len(data.get('evidence','').strip())<10 or not reviewer or not reviewed_at:raise ValueError('Explicit authenticated engineering source evidence is required.')
    kind=data['kind']
    if kind not in FIELD_SCHEMA:raise ValueError('Unsupported native component profile kind.')
    allowed={f['key'] for f in FIELD_SCHEMA[kind]}
    if set(data.get('values',{}))-allowed:raise ValueError('Unsupported field in this bounded native component profile.')
    for value in data.get('values',{}).values():
        if not isinstance(value,(str,int,bool,type(None))) or isinstance(value,str) and len(value)>3000:raise ValueError('Use explicit canonical scalar values or null; no hidden expressions or nested data.')
    sheets={s['id']:s for s in project.get('sheets',[])}
    if data.get('source_sheet_id') and data['source_sheet_id'] not in sheets:raise ValueError('Select an actual current source drawing sheet.')
    if data.get('component_id') and not any(c['id']==data['component_id'] for c in requirements(project)[0]):raise ValueError('Select a current physical component requirement.')
    if data.get('point_id') and not any(n['id']==data['point_id'] for n in project['nodes']):raise ValueError('Select a current physical point; retired/foreign UUIDs cannot become native nodes.')
    if data.get('element_id') and not any(e['id']==data['element_id'] for e in _edge_rows(project)):raise ValueError('Select an active explicit-route element.')
    stored=project.setdefault('analysis_model',{}).setdefault('native_components',[])
    previous=next((r for r in stored if r['id']==record_id),None)
    if record_id and not previous:raise ValueError('Native component record not found.')
    if not previous and len(stored)>=MAX_RECORDS:raise ValueError('Native component record allowance reached.')
    record={**deepcopy(data),'id':record_id or identity(project['id'],'native-component',len(stored)+1,reviewed_at,kind),
        'reviewed_by':reviewer,'reviewed_at':reviewed_at,'engineering_approved':False}
    record['source_context_sha256']=digest(_context(project,record))
    if previous:
        project['analysis_model'].setdefault('native_component_history',[]).append(deepcopy(previous));stored[stored.index(previous)]=record
    else:stored.append(record)
    return deepcopy(record)
