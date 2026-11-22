"""Documented CAESAR II 15.1 neutral-file subset: straight pipe candidates.

Contract sources: Hexagon CAESAR II Users Guide 15.1, Neutral File sections
337038/337039/337040/337041/1532581/337060/337061. Not a stress solver or
an assertion of qualification by the proprietary application.
"""
from decimal import Decimal,InvalidOperation,localcontext
import math

from packages.automation.recognize import identity
from packages.engineering import topology

PROFILE='caesar-15.1-straight-pipe-v1'
REQUIRED=('dx_mm','dy_mm','dz_mm','od_mm','wall_mm','corrosion_mm','material_code','temperature_c','pressure_mpa',
          'elastic_modulus_mpa','hot_modulus_mpa','poisson_ratio','pipe_density_kg_m3','fluid_density_kg_m3',
          'insulation_thickness_mm','cold_allowable_mpa','hot_allowable_mpa')
OPTIONAL_SECTIONS=('NODENAME','BEND','RIGID','EXPJT','RESTRANT','DISPLMNT','FORCMNT','UNIFORM','WIND','OFFSETS')


def assess(project):
    model=project.get('analysis_model',{});nodes=project['nodes'];edges=topology(nodes)['edges'];by_id={n['id']:n for n in nodes};entered={e['id']:e for e in model.get('elements',[])};missing=[]
    if not edges:missing.append('A reviewed connected pipe route is required.')
    from packages.physical import audit as physical_audit
    if physical_audit(project)['components']:missing.append('Component ports/auxiliaries are not represented by this straight-pipe-only native profile.')
    if project.get('physical_model') or project.get('analysis_model'):
        from packages.physical.constraints import solve
        if solve(project)['issues']:missing.append('Resolve all dimensional constraint conflicts, stale sources and stale accepted solutions before native export.')
    if any(n.get('station_mm') is None or n.get('verification')=='proposed' or not n.get('evidence') for n in nodes):missing.append('Accept the engineering station/evidence for every model point first.')
    unsupported=sorted({n['kind'] for n in nodes if n['kind']!='endpoint'})
    if unsupported:missing.append('This first neutral profile supports straight pipe/endpoints only; component-specific data are required for '+', '.join(unsupported)+'.')
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
                if not any(delta):missing.append('A straight pipe element cannot have zero length.')
                if by_id[a].get('station_mm') is not None and by_id[b].get('station_mm') is not None:
                    distance=sum(v*v for v in delta).sqrt();station_gap=abs(Decimal(by_id[b]['station_mm'])-Decimal(by_id[a]['station_mm']))
                    if abs(distance-station_gap)>Decimal('.01'):missing.append(f"Element {by_id[a].get('number')} → {by_id[b].get('number')}: signed geometry and accepted straight-pipe station distance conflict.")
                vectors[(a,b)]=delta;vectors[(b,a)]=tuple(-v for v in delta)
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
        if len(neighbors)>2:missing.append('Tee/branch auxiliaries require a separately qualified component profile.')
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
    return {'profile':PROFILE,'target':'CAESAR II 15.1','available':not missing,'qualified_application_roundtrip':False,'missing':list(dict.fromkeys(missing)), 'status':'IMPORT_CANDIDATE_ONLY'}


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


def neutral_file(project):
    check=assess(project)
    if not check['available']:raise ValueError('Native CAESAR data incomplete: '+'; '.join(check['missing'][:8]))
    model=project['analysis_model'];by_id={n['id']:n for n in project['nodes']};edges=topology(project['nodes'])['edges'];entered={e['id']:e for e in model['elements']}
    with localcontext() as context:
        context.prec=40
        inch=Decimal('25.4');pound=Decimal('0.45359237');psi=Decimal('4.4482216152605')/(Decimal('.0254')**2);mpa_to_psi=Decimal(1000000)/psi
        density_factor=(Decimal('.0254')**3)/pound
        def length(value):
            converted=Decimal(value)/inch;encoded=_real(converted)
            if abs(Decimal(encoded)*inch-Decimal(value))>Decimal('.01'):raise ValueError('Native field rounding exceeds 0.01 mm; use a reviewed precision/profile decision.')
            return converted
        def temperature(value):return Decimal(value)*Decimal('1.8')+32
        title=['CAESAR ISO - STRAIGHT PIPE IMPORT CANDIDATE','NOT VERIFIED FOR MODELLING; NO STRESS ANALYSIS HAS BEEN RUN',f"Project: {project['title']}",f"Revision: {project['version']}",f"Profile: {PROFILE}",'Native file uses explicit English units; canonical website/workbook units remain mm/N/MPa/C.','Local origin at first main point is an explicitly selected model frame.','Validate geometry, code/material IDs and all properties in CAESAR II after conversion.']
        titles=[]
        for text in title:
            text.encode('cp1252')
            if any(ord(c)<32 for c in text):raise ValueError('Control characters in native title.')
            titles.extend(text[i:i+75] for i in range(0,len(text),75))
        lines=['#$ VERSION','  '+_real(15)+_real('15.1')+f'{1252:8d}']
        lines += ['  '+(titles[i] if i<len(titles) else '').ljust(75) for i in range(60)]
        lines += ['#$ CONTROL']+_records([len(edges),0,0,0,0,0],True)
        auxiliary=[0]*13;auxiliary[9]=len(edges);auxiliary[11]=1 if model['vertical_axis']=='Z' else 0
        lines += _records(auxiliary,True)+['#$ ELEMENTS']
        materials=[];allowables=[]
        for i,edge in enumerate(edges):
            data=entered[identity(project['id'],edge['from'],edge['to'])];a,b=by_id[edge['from']],by_id[edge['to']]
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
            pointers=[0]*15;pointers[9]=i+1;lines+=_records(pointers,True)
            materials.append(int(data['material_code']))
            values=[Decimal(0)]*168;values[0]=Decimal(data['cold_allowable_mpa'])*mpa_to_psi;values[1]=Decimal(data['hot_allowable_mpa'])*mpa_to_psi;values[11]=Decimal(model['piping_code_id']);allowables.append(values)
        lines+=['#$ AUX_DATA']+['#$ '+name for name in OPTIONAL_SECTIONS]+['#$ ALLOWBLS']
        for values in allowables:lines+=_records(values)
        lines+=['#$ SIF&TEES','#$ REDUCERS','#$ FLANGES','#$ EQUIPMNT','#$ MISCEL_1']+_records(materials)
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
