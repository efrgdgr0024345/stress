"""Documented CAESAR II 15.1 neutral candidates with reviewed auxiliary inputs.

Contract sources: Hexagon CAESAR II Users Guide 15.1, Neutral File sections
337038/337039/337040/337041/1532581/337060/337061. Not a stress solver or
an assertion of qualification by the proprietary application.
"""
from decimal import Decimal,InvalidOperation,localcontext
import math

from packages.automation.recognize import identity
from packages.engineering import topology,topology_assigned,source_location_reviewed

PROFILE='caesar-15.1-reviewed-components-v1'
REQUIRED=('dx_mm','dy_mm','dz_mm','od_mm','wall_mm','corrosion_mm','material_code','temperature_c','pressure_mpa',
          'elastic_modulus_mpa','hot_modulus_mpa','poisson_ratio','pipe_density_kg_m3','fluid_density_kg_m3',
          'insulation_thickness_mm','cold_allowable_mpa','hot_allowable_mpa')
OPTIONAL_SECTIONS=('NODENAME','BEND','RIGID','EXPJT','RESTRANT','DISPLMNT','FORCMNT','UNIFORM','WIND','OFFSETS')


def assess(project):
    model=project.get('analysis_model',{});nodes=project['nodes'];edges=topology(nodes)['edges'];by_id={n['id']:n for n in nodes};entered={e['id']:e for e in model.get('elements',[])};missing=[]
    from packages.workbooks.cii_components import native_component_plan
    native=native_component_plan(project)
    missing.extend(i['code']+': '+i['message'] for i in native['issues'])
    if native.get('bends'):missing.append('BEND generation remains blocked until the native geometry bridge and 15.1 field-layout contract are verified.')
    supported_points=set(native.get('supported_point_ids',[]))
    covered_components=set(native.get('covered_component_ids',[]))
    tee_points={t['point_id'] for t in native.get('tees',[])}
    if any(not topology_assigned(n) for n in nodes):missing.append('Every source point needs explicit accepted route/order; unassigned locations cannot be omitted from the native model.')
    if any(n.get('source_observation') and not source_location_reviewed(n,{s['id']:s for s in project['sheets']}) or n.get('source_review_reasons') for n in nodes):
        missing.append('Review current source anchors and resolve typed source-interface reasons before native export.')
    if not edges:missing.append('A reviewed connected pipe route is required.')
    from packages.engineering.graph_review import audit_graph
    if audit_graph(project)['structural_issues']:missing.append('Resolve invalid, unassigned or stale source topology before native export.')
    from packages.physical.source_exceptions import source_exception_report
    if source_exception_report(project)['active']:missing.append('Resolve the current source-linked physical-interface and dimension-witness exceptions before native export.')
    from packages.engineering.continuations import audit as continuation_audit
    if continuation_audit(project):missing.append('Resolve provisional, stale or conflicting continuation identities before native export.')
    from packages.physical import audit as physical_audit
    physical=physical_audit(project)
    if any(c['id'] not in covered_components for c in physical['components']):missing.append('Every physical component needs a supported current reviewed native representation; no component may be silently omitted.')
    if physical['issues']:missing.append('Resolve all physical component/interface source proof before native export.')
    if project.get('physical_model') or project.get('analysis_model'):
        from packages.physical.constraints import solve
        if solve(project)['issues']:missing.append('Resolve all dimensional constraint conflicts, stale sources and stale accepted solutions before native export.')
    from packages.physical.stations import solve_stations,station_pair_comparable
    station_model=project.get('physical_model',{})
    if (station_model.get('station_constraints') or station_model.get('retired_station_constraints') or any(n.get('station_proof') or n.get('manual_station_basis') for n in nodes)) and solve_stations(project)['issues']:
        missing.append('Resolve unproved station datums, conflicting along-route lengths and stale accepted station proofs before native export.')
    if any(n.get('station_mm') is None or n.get('verification')=='proposed' or not n.get('evidence') for n in nodes):missing.append('Accept the engineering station/evidence for every model point first.')
    unsupported=sorted({n['kind'] for n in nodes if n['kind'] not in ('endpoint','continuation') and n['id'] not in supported_points})
    if unsupported:missing.append('Current supported component-specific native data are required for '+', '.join(unsupported)+'.')
    main=sorted((n for n in nodes if n['route']=='main'),key=lambda n:(n['order'],n['id']))
    if not main or not model.get('local_origin_confirmed') or model.get('origin_point_id')!=main[0]['id']:missing.append('Declare the current first main point as the local model origin; surveyed coordinates are not invented.')
    try:
        ambient=Decimal(model['ambient_temperature_c'])
        if not ambient.is_finite() or not Decimal('-273.15')<=ambient<=2000:raise ValueError()
    except (KeyError,TypeError,ValueError,InvalidOperation):missing.append('A finite ambient temperature from -273.15 to 2000 Celsius is required.')
    if not isinstance(model.get('piping_code_id'),int) or not 1<=model['piping_code_id']<=999:missing.append('The explicit CAESAR piping code ID is required.')
    if model.get('vertical_axis') not in ('Y','Z'):missing.append('Select the vertical model axis.')
    adjacent={n['id']:set() for n in nodes};vectors={}
    for edge in edges:
        a,b=edge['from'],edge['to'];adjacent[a].add(b);adjacent[b].add(a)
        data=entered.get(identity(project['id'],a,b),{})
        absent=[k for k in REQUIRED if data.get(k) is None]
        if absent:missing.append(f"Element {by_id[a].get('number')} → {by_id[b].get('number')}: "+', '.join(absent))
        else:
            try:
                for key in REQUIRED:
                    value=Decimal(data[key])
                    if not value.is_finite() or value.copy_abs()>Decimal('1000000000000'):raise ValueError()
                material=int(data['material_code'])
                if not 1<=material<=699:raise ValueError()
                delta=tuple(Decimal(data[k]) for k in ('dx_mm','dy_mm','dz_mm'))
                if not any(delta):missing.append('A native pipe/rigid element cannot have zero length.')
                if station_pair_comparable(by_id[a],by_id[b]):
                    with localcontext() as context:
                        context.prec=200
                        distance=sum(v*v for v in delta).sqrt();station_gap=abs(Decimal(by_id[b]['station_mm'])-Decimal(by_id[a]['station_mm']))
                        disagreement=abs(distance-station_gap)>Decimal('.01')
                    if disagreement:missing.append(f"Element {by_id[a].get('number')} → {by_id[b].get('number')}: signed geometry and accepted straight-pipe station distance conflict.")
                vectors[(a,b)]=delta;vectors[(b,a)]=tuple(v.copy_negate() for v in delta)
                if Decimal(data['od_mm'])<=0 or not 0<Decimal(data['wall_mm'])*2<Decimal(data['od_mm']):missing.append('Pipe OD/wall values are inconsistent.')
                if not 0<Decimal(data['poisson_ratio'])<Decimal('.5'):missing.append('The isotropic straight-pipe profile requires Poisson ratio between zero and 0.5.')
                if any(Decimal(data[k])<=0 for k in ('elastic_modulus_mpa','hot_modulus_mpa','pipe_density_kg_m3','cold_allowable_mpa','hot_allowable_mpa')):missing.append('Moduli, pipe density and allowable stresses must be positive.')
                if any(Decimal(data[k])<0 for k in ('corrosion_mm','pressure_mpa','fluid_density_kg_m3','insulation_thickness_mm')):missing.append('Pressure, corrosion, insulation and fluid density cannot be negative.')
                if Decimal(data['corrosion_mm'])>=Decimal(data['wall_mm']):missing.append('Corrosion allowance must be less than the wall thickness.')
                if Decimal(data['temperature_c'])<Decimal('-273.15'):missing.append('Temperature cannot be below absolute zero.')
                if Decimal(data['insulation_thickness_mm'])>0 and data.get('insulation_density_kg_m3') is None:missing.append('Insulated pipe needs insulation density.')
                if data.get('insulation_density_kg_m3') is not None:
                    density=Decimal(data['insulation_density_kg_m3'])
                    if not density.is_finite() or density<0 or density>Decimal('1000000000000'):raise ValueError()
            except (ValueError,InvalidOperation):missing.append('Material IDs must be 1–699 and all supplied native-profile numbers must be finite.')
    if nodes:
        visited=set();stack=[nodes[0]['id']]
        while stack:
            v=stack.pop()
            if v not in visited:visited.add(v);stack+=list(adjacent[v]-visited)
        if len(visited)!=len(nodes):missing.append('Disconnected segments need explicit origin/correspondence data; this profile exports one connected route.')
    for point,neighbors in adjacent.items():
        if len(neighbors)>2:
            if point not in tee_points or len(neighbors)!=3:missing.append('A junction needs one current supported three-way tee definition; unclassified or higher-order branches are blocked.')
        elif len(neighbors)==2:
            a,b=sorted(neighbors);u=vectors.get((point,a));v=vectors.get((point,b))
            if u is not None and v is not None:
                cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                if any(cross) or sum(x*y for x,y in zip(u,v))>=0:missing.append('Direction changes require explicit bend/component data; they cannot be emitted as unqualified sharp pipe corners.')
    if any(n.get('number') is None or not 1<=n['number']<=9999999 for n in nodes):missing.append('Node numbers must fit the documented seven-significant-digit numeric profile.')
    if len({n.get('number') for n in nodes})!=len(nodes):missing.append('This neutral profile requires unique node numbers across the connected model.')
    try:
        for text in [project['title']]+[e['line_id'] for e in edges]:
            if any(ord(c)<32 for c in text):raise ValueError()
            text.encode('cp1252')
        if any(len(e['line_id'])>500 for e in edges):raise ValueError()
    except (ValueError,UnicodeEncodeError):missing.append('Native labels must fit their Windows-1252 text fields without control characters.')
    return {'profile':PROFILE,'target':'CAESAR II 15.1','available':not missing,'qualified_application_roundtrip':False,'missing':list(dict.fromkeys(missing)),
        'component_counts':{'rigids':len(native.get('rigids',[])),'tees':len(native.get('tees',[])),
            'restraint_blocks':len(native.get('restraint_blocks',[])),'bends':0},
        'bend_contract_verified':False,'status':'IMPORT_CANDIDATE_ONLY'}


def _real(value):
    value=Decimal(value)
    if not value.is_finite():raise ValueError('Non-finite neutral-file value.')
    mantissa,exponent=format(value,'.6E').split('E')
    result=mantissa+'E'+f'{int(exponent):+03d}'
    if value==0:result='0.000000E+00'
    if len(result)>13:raise ValueError('Value exceeds the native field width.')
    return result.rjust(13)


def _records(values,integer=False):
    return ['  '+''.join(f'{int(v):13d}' if integer else _real(v) for v in values[i:i+6]) for i in range(0,len(values),6)]


def _string(value,width=500):
    value=str(value)
    if any(ord(c)<32 for c in value):raise ValueError('Control characters are not accepted in native file labels.')
    value.encode('cp1252')
    if len(value)>width:raise ValueError('Native text field exceeds its documented length.')
    return ' '*7+f'{len(value):5d}'+' '+value


def _component_blocks(project,edges,plan):
    """Group reviewed records into documented 1-based auxiliary blocks."""
    order={identity(project['id'],e['from'],e['to']):i for i,e in enumerate(edges)}
    def key(record):return (order.get(record['element_id'],len(edges)),record.get('id',''))
    rigids=sorted(plan.get('rigids',[]),key=key)
    if len({r['element_id'] for r in rigids})!=len(rigids):
        raise ValueError('A native element cannot select more than one rigid definition.')
    tees={}
    for record in sorted(plan.get('tees',[]),key=key):tees.setdefault(record['element_id'],[]).append(record)
    tee_blocks=[]
    for element_id,records in sorted(tees.items(),key=lambda item:order.get(item[0],len(edges))):
        if len(records)>2 or len({r['point_id'] for r in records})!=len(records):
            raise ValueError('A SIF/TEE auxiliary block supports at most two distinct reviewed intersection nodes.')
        edge=edges[order[element_id]] if element_id in order else None
        records.sort(key=lambda r:0 if edge and r['point_id']==edge['from'] else 1)
        tee_blocks.append({'element_id':element_id,'tees':records})
    restraints=sorted(plan.get('restraint_blocks',[]),key=key)
    if len({r['element_id'] for r in restraints})!=len(restraints):
        raise ValueError('Each native carrier element must select one bounded restraint block.')
    if any(len(r['restraints'])>6 for r in restraints):raise ValueError('A restraint block supports at most six explicitly reviewed restraints.')
    if any(r['element_id'] not in order for r in rigids+tee_blocks+restraints):
        raise ValueError('Native component data refers to a retired or nonexistent element.')
    return {'rigids':rigids,'tee_blocks':tee_blocks,'restraint_blocks':restraints,
        'rigid_pointer':{r['element_id']:i+1 for i,r in enumerate(rigids)},
        'tee_pointer':{r['element_id']:i+1 for i,r in enumerate(tee_blocks)},
        'restraint_pointer':{r['element_id']:i+1 for i,r in enumerate(restraints)}}


def _tee_slot(record=None):
    values=[Decimal(0)]*42
    # An absent second node is represented by Node=0. The two code-note fields
    # retain the documented unspecified sentinel, rather than a cleared option.
    values[22]=values[23]=Decimal('9999.99')
    if record is None:return values
    fields={0:'node_number',1:'tee_type',2:'in_plane_sif',3:'out_plane_sif',
        12:'in_plane_index',13:'out_plane_index',14:'axial_sif',15:'torsion_sif',
        16:'pressure_sif',17:'pressure_index',22:'code_note_1',23:'code_note_2',
        24:'axial_index',25:'torsion_index'}
    try:
        for index,name in fields.items():values[index]=Decimal(str(record[name]))
    except (KeyError,TypeError,InvalidOperation) as error:
        raise ValueError('A reviewed SIF/TEE record is missing an explicit canonical field.') from error
    if values[22] not in (0,1,Decimal('9999.99')) or values[23] not in (0,1,Decimal('9999.99')):
        raise ValueError('SIF/TEE code-note options must be selected, cleared or explicitly unspecified.')
    return values


def neutral_file(project):
    check=assess(project)
    if not check['available']:raise ValueError('Native CAESAR data incomplete: '+'; '.join(check['missing'][:8]))
    from packages.workbooks.cii_components import native_component_plan
    model=project['analysis_model'];by_id={n['id']:n for n in project['nodes']};edges=topology(project['nodes'])['edges'];entered={e['id']:e for e in model['elements']}
    blocks=_component_blocks(project,edges,native_component_plan(project))
    with localcontext() as context:
        context.prec=40
        inch=Decimal('25.4');pound=Decimal('0.45359237');lbf=Decimal('4.4482216152605');psi=lbf/(Decimal('.0254')**2);mpa_to_psi=Decimal(1000000)/psi
        density_factor=(Decimal('.0254')**3)/pound
        def length(value):
            converted=Decimal(value)/inch;encoded=_real(converted)
            if abs(Decimal(encoded)*inch-Decimal(value))>Decimal('.01'):raise ValueError('Native field rounding exceeds 0.01 mm; use a reviewed precision/profile decision.')
            return converted
        def temperature(value):return Decimal(value)*Decimal('1.8')+32
        title=['CAESAR ISO - REVIEWED INPUT IMPORT CANDIDATE','NOT VERIFIED FOR MODELLING; NO STRESS ANALYSIS HAS BEEN RUN',f"Project: {project['title']}",f"Revision: {project['version']}",f"Profile: {PROFILE}",'Native file uses explicit English units; canonical website/workbook units remain mm/N/MPa/C.','Local origin at first main point is an explicitly selected model frame.','Validate geometry, code/material IDs and all properties in CAESAR II after conversion.',
            'BEND generation is blocked pending verified native geometry and field contracts.']
        titles=[]
        for text in title:
            text.encode('cp1252')
            if any(ord(c)<32 for c in text):raise ValueError('Control characters in native title.')
            titles.extend(text[i:i+75] for i in range(0,len(text),75))
        lines=['#$ VERSION','  '+_real(15)+_real('15.1')+f'{1252:8d}']
        lines += ['  '+(titles[i] if i<len(titles) else '').ljust(75) for i in range(60)]
        lines += ['#$ CONTROL']+_records([len(edges),0,0,0,0,0],True)
        auxiliary=[0]*13;auxiliary[1]=len(blocks['rigids']);auxiliary[3]=len(blocks['restraint_blocks'])
        auxiliary[9]=len(edges);auxiliary[10]=len(blocks['tee_blocks']);auxiliary[11]=1 if model['vertical_axis']=='Z' else 0
        lines += _records(auxiliary,True)+['#$ ELEMENTS']
        materials=[];allowables=[]
        for i,edge in enumerate(edges):
            element_id=identity(project['id'],edge['from'],edge['to']);data=entered[element_id];a,b=by_id[edge['from']],by_id[edge['to']]
            rel=[Decimal(0)]*53
            dx,dy,dz=(Decimal(data[k]) for k in ('dx_mm','dy_mm','dz_mm'))
            # Canonical axes are East/North/Up. Preserve handedness when the
            # target uses Y-up: native X=East, Y=Up, Z=South.
            if model['vertical_axis']=='Y':dy,dz=dz,-dy
            rel[:7]=[Decimal(a['number']),Decimal(b['number']),length(dx),length(dy),length(dz),length(data['od_mm']),length(data['wall_mm'])]
            rel[7]=length(data['insulation_thickness_mm']);rel[8]=length(data['corrosion_mm']);rel[9]=temperature(data['temperature_c']);rel[18]=Decimal(data['pressure_mpa'])*mpa_to_psi
            rel[27]=Decimal(data['elastic_modulus_mpa'])*mpa_to_psi;rel[28]=Decimal(data['poisson_ratio']);rel[29]=Decimal(data['pipe_density_kg_m3'])*density_factor
            rel[30]=Decimal(data.get('insulation_density_kg_m3') or 0)*density_factor;rel[31]=Decimal(data['fluid_density_kg_m3'])*density_factor;rel[36]=Decimal(data['hot_modulus_mpa'])*mpa_to_psi
            lines+=_records(rel)+[_string(f"E-{a['number']}-{b['number']}"),_string(edge['line_id'])]+_records([0,1])
            pointers=[0]*15;pointers[1]=blocks['rigid_pointer'].get(element_id,0);pointers[3]=blocks['restraint_pointer'].get(element_id,0)
            pointers[9]=i+1;pointers[10]=blocks['tee_pointer'].get(element_id,0);lines+=_records(pointers,True)
            materials.append(int(data['material_code']))
            values=[Decimal(0)]*168;values[0]=Decimal(data['cold_allowable_mpa'])*mpa_to_psi;values[1]=Decimal(data['hot_allowable_mpa'])*mpa_to_psi;values[11]=Decimal(model['piping_code_id']);allowables.append(values)
        lines+=['#$ AUX_DATA','#$ NODENAME','#$ BEND','#$ RIGID']
        for rigid in blocks['rigids']:lines+=_records([Decimal(rigid['weight_n'])/lbf,rigid['rigid_type']])
        lines+=['#$ EXPJT','#$ RESTRANT']
        for block in blocks['restraint_blocks']:
            for index in range(6):
                restraint=block['restraints'][index] if index<len(block['restraints']) else None
                if restraint:
                    # This narrow profile accepts global TARGET_CAESAR_AXES
                    # translational types only; CNODE/direction overrides are
                    # explicitly absent, not inferred from a support callout.
                    values=[restraint['node_number'],restraint['type_code'],
                        Decimal(restraint['stiffness_n_per_mm'])*inch/lbf,length(restraint['gap_mm']),
                        restraint['friction_coefficient'],0,0,0,0]
                    tag=restraint.get('support_tag') or '';guid=restraint.get('support_guid') or ''
                else:values=[0]*9;tag=guid=''
                lines+=_records(values[:6])+_records(values[6:])+[_string(tag,100),_string(guid,100)]
        lines+=['#$ DISPLMNT','#$ FORCMNT','#$ UNIFORM','#$ WIND','#$ OFFSETS','#$ ALLOWBLS']
        for values in allowables:lines+=_records(values)
        lines+=['#$ SIF&TEES']
        for block in blocks['tee_blocks']:
            for index in range(2):lines+=_records(_tee_slot(block['tees'][index] if index<len(block['tees']) else None))
        lines+=['#$ REDUCERS','#$ FLANGES','#$ EQUIPMNT','#$ MISCEL_1']+_records(materials)
        # No nozzles/hangers in this deliberately bounded profile. Documented
        # control/sentinel slots below are not fabricated engineering properties.
        lines+=['  '+f'{0:13d}'+''.join(_real(v) for v in [0,0,'9999.99',0,0])]
        lines+=['  '+''.join(f'{v:13d}' for v in [1,0,0,0,1])]
        lines+=['  '+''.join(f'{v:13d}' for v in [0,0,0,1])+_real(0)+f'{0:13d}']
        lines+=['  '+f'{0:13d}'+_real(0)+_real(temperature(model['ambient_temperature_c']))+''.join(f'{v:13d}' for v in [0,0,1])]
        lines+=['  '+''.join(f'{v:13d}' for v in [1,0,0,0])+_real(0)+f'{0:13d}','  '+f'{0:13d}','  '+f'{0:13d}']
        conversions=[Decimal(1)]*22;conversions[7]=Decimal(0)
        lines+=['#$ UNITS']+_records(conversions)
        labels=[('English',15),('OFF',3),('in',3),('lb',3),('lb',3),('in.lb',6),('in.lb',6),('lb/sq.in',10),('F',1),('F',1),('lb/sq.in',10),('lb/sq.in',10),('lb/cu.in',10),('lb/cu.in',10),('lb/cu.in',10),('lb/in',7),('in.lb/deg',10),('lb/in',7),('g',3),('lb/sq.in',10),('in',3),('in',3),('in',3),('in',3)]
        lines+=['  '+value.ljust(width) for value,width in labels]
        first=by_id[model['origin_point_id']]
        lines+=['#$ COORDS','  '+f'{1:13d}','  '+f"{first['number']:13d}"+''.join(f'{Decimal(0):13.4f}' for _ in range(3))]
        return ('\r\n'.join(lines)+'\r\n').encode('cp1252')
