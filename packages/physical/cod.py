"""Theoretical COD from proved engineering centreline legs, never page angles."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import hashlib
import json

CONVENTION='THEORETICAL_CENTRELINE_INTERSECTION'


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def decimal_exact(value):
    denominator=value.denominator;twos=fives=0
    while denominator%2==0:denominator//=2;twos+=1
    while denominator%5==0:denominator//=5;fives+=1
    if denominator!=1:return None
    places=max(twos,fives)
    scaled=value.numerator*2**(places-twos)*5**(places-fives)
    result=Decimal(str(scaled)+'e-'+str(places))
    if len(result.as_tuple().digits)>50 or abs(result)>Decimal('1000000000000'):return None
    return str(result)


def intersect_legs(points):
    """Four independent physical XYZ points: incoming far/near, outgoing near/far."""
    if len(points)!=4 or any(len(p)!=3 for p in points):raise ValueError('Four complete engineering XYZ leg points are required.')
    a,b,c,d=[[Fraction(str(v)) for v in point] for point in points]
    v=[b[i]-a[i] for i in range(3)];w=[d[i]-c[i] for i in range(3)];rhs=[c[i]-a[i] for i in range(3)]
    determinants=[(v[j]*w[i]-v[i]*w[j],i,j) for i,j in ((0,1),(0,2),(1,2))]
    determinant,i,j=max(determinants,key=lambda item:abs(item[0]))
    if not determinant:return {'status':'COD_NOT_UNIQUELY_CONSTRAINED','coordinates_mm':None}
    t=(rhs[j]*w[i]-rhs[i]*w[j])/determinant
    u=(v[i]*rhs[j]-v[j]*rhs[i])/determinant
    first=[a[k]+t*v[k] for k in range(3)];second=[c[k]+u*w[k] for k in range(3)]
    if first!=second:return {'status':'COD_LEG_COORDINATES_CONFLICT','coordinates_mm':None,'residual_exact_mm':[str(second[k]-first[k]) for k in range(3)]}
    if not t>1 or not u<0:return {'status':'COD_TANGENT_ORIENTATION_REVIEW','coordinates_mm':None}
    values=[decimal_exact(value) for value in first]
    if any(value is None for value in values):return {'status':'COD_EXACT_PRECISION_REVIEW','coordinates_mm':None,'exact_rational_mm':list(map(str,first))}
    return {'status':'COD_PROPOSED','coordinates_mm':dict(zip(('X','Y','Z'),values)),
            'exact_rational_mm':list(map(str,first)),'parameters':{'incoming':str(t),'outgoing':str(u)}}


def proposals(project):
    from packages.physical import requirements
    from packages.physical.constraints import solve,base_observations
    components=[c for c in requirements(project)[0] if c['kind']=='elbow']
    if not components:return []
    base=deepcopy(project)
    base.setdefault('physical_model',{})['constraints']=[c for c in base.get('physical_model',{}).get('constraints',[]) if not c.get('cod_derivation')]
    solution=solve(base);coordinates={p['point_id']:p['axes'] for p in solution['coordinates']}
    basis=digest(sorted(base_observations(project),key=lambda c:c['id']))
    nodes={n['id']:n for n in project['nodes']};sheets={s['id']:s for s in project['sheets']};result=[]
    for component in components:
        record={'component_id':component['id'],'status':'COD_SOURCE_CONVENTION_REQUIRED','point_id':None,
                'coordinates_mm':None,'station_mm':None,'drawing_pixels_used':False,'radius_mm':None}
        result.append(record)
        port=component['ports'].get('theoretical_cod');proof=port.get('proof',{}) if port else {}
        target=nodes.get(port.get('point_id')) if port else None;sheet=sheets.get(proof.get('sheet_id'))
        source=bool(sheet and (proof.get('content_hash')==sheet.get('content_hash') if sheet.get('content_hash') else proof.get('source_sha256')==sheet.get('sha256')))
        instance=next((i for i in target['instances'] if i['sheet_id']==proof.get('sheet_id')),None) if target else None
        box=proof.get('bbox',[])
        current_anchor=bool(instance and len(box)==4 and box[0]<=instance['anchor'][0]<=box[2] and box[1]<=instance['anchor'][1]<=box[3])
        if (not target or target['kind']!='elbow' or component.get('verification')!='reviewed' or not source or not current_anchor
                or proof.get('dimension_convention_kind')!=CONVENTION):continue
        record['point_id']=target['id']
        ordered=sorted((n for n in project['nodes'] if n['line_id']==target['line_id'] and n['route']==target['route']),key=lambda n:(n['order'],n['id']))
        if len({n['order'] for n in ordered})!=len(ordered):record['status']='COD_ROUTE_ORDER_AMBIGUOUS';continue
        if target['route']!='main' and ordered and ordered[0].get('takeoff_id') in nodes:
            ordered=[nodes[ordered[0]['takeoff_id']]]+ordered
        index=next(i for i,n in enumerate(ordered) if n['id']==target['id'])
        if index<2 or index+2>=len(ordered):record['status']='COD_LEG_POINTS_REQUIRED';continue
        legs=ordered[index-2:index]+ordered[index+1:index+3]
        record['leg_point_ids']=[n['id'] for n in legs]
        values=[[coordinates.get(n['id'],{}).get(axis,{}).get('value_mm') for axis in ('X','Y','Z')] for n in legs]
        if any(v is None for point in values for v in point):record['status']='COD_COORDINATE_EVIDENCE_REQUIRED';continue
        record.update(intersect_legs(values))
        if record['status']!='COD_PROPOSED':continue
        known=coordinates.get(target['id'],{})
        if any(known.get(axis,{}).get('value_mm') is not None and Decimal(known[axis]['value_mm'])!=Decimal(value) for axis,value in record['coordinates_mm'].items()):
            record.update(status='COD_CONFLICTS_WITH_ACCEPTED_SOURCE',coordinates_mm=None);continue
        record['source_sheet_id']=proof['sheet_id']
        record['derivation']={'basis_sha256':basis,'association_sha256':digest(port),
            'component_id':component['id'],'leg_point_ids':record['leg_point_ids'],'convention':CONVENTION,
            'exact_rational_mm':record['exact_rational_mm']}
        accepted=[c for c in project.get('physical_model',{}).get('constraints',[]) if c.get('cod_derivation',{}).get('component_id')==component['id']]
        if len(accepted)==3 and {c['axis'] for c in accepted}=={'X','Y','Z'} and all(c.get('verification')=='reviewed' and
            c['cod_derivation']==record['derivation'] and c['value_mm']==record['coordinates_mm'][c['axis']] for c in accepted):
            record['status']='COD_ACCEPTED'
    return result
