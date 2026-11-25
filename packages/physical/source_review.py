"""Source-located review points, independent from accepted topology and stations."""
from copy import deepcopy
from pathlib import Path
import json
from packages.physical import identity,prepare,POLICIES
from packages.automation.recognize import identity as recognition_identity

PROFILE=Path(__file__).with_name('profiles')/'1010-reviewed.json'


def point_label(point):
    return str(point['number']) if point.get('number') is not None else point.get('review_label','Unnumbered')


def source_profile():
    return json.loads(PROFILE.read_text()) if PROFILE.is_file() else None


def incoming_materials(project,observations):
    """Keep this exact source's prepared review inventory during OCR refresh.

    Fresh raw OCR remains in automation evidence. It cannot silently duplicate
    source-profile records or overwrite an engineer's material corrections.
    A changed source hash is deliberately outside this protection.
    """
    state=project.get('source_review',{})
    sha=state.get('profile_source_sha256') if state.get('prepared') else None
    protected={s['id'] for s in project['sheets'] if sha and s['sha256']==sha}
    return [m for m in observations if m['sheet_id'] not in protected]


def _profile_materials(project,profile,matching):
    """Actual retained source observations are unreviewed, never catalog facts."""
    tombstones=set(project.get('automation_tombstones',{}).get('material_ids',[]))
    for observed in profile.get('material_observations',[]):
        sheet=matching.get(observed['page_index'])
        if not sheet:continue
        existing=next((m for m in project['materials'] if m['sheet_id']==sheet['id'] and m['item_no']==observed['item_no']),None)
        if not existing:
            uid=identity(project['id'],'source-review-material',sheet['sha256'],observed['page_index'],observed['item_no'])
            if uid in tombstones:continue
            existing={**deepcopy(observed),'id':uid,'sheet_id':sheet['id'],'origin':'source-review-profile','verification':'proposed','observed':0}
            project['materials'].append(existing)
        elif existing.get('verification')!='reviewed' and existing.get('quantity_unit')=='unresolved' and observed.get('source_review_notes'):
            existing.setdefault('source_review_history',[]).append({k:deepcopy(existing.get(k)) for k in ('size','quantity','quantity_raw','quantity_value','quantity_unit')})
            existing.update({k:deepcopy(observed[k]) for k in ('size','quantity','quantity_raw','quantity_value','quantity_unit','source_review_notes')})
        if observed['page_index']==1 and observed['item_no']=='11' and existing['family']=='other':
            existing['connection_profile']={'kind':'TWO_PROCESS_ENDS_CLASSIFICATION_UNCONFIRMED',
                'source_sha256':sheet['sha256'],'evidence':'The actual PV-7680 inline source body has two visible process interfaces. Valve/instrument classification remains unproved; both end requirements are proposals.'}


def _profile_flanges(project,profile,matching):
    """Same detector identity and source paths; no fixture-specific engineering model."""
    features=project.setdefault('automation',{}).setdefault('feature_proposals',[])
    for association in profile.get('flange_material_associations',[]):
        sheet=matching.get(association['page_index'])
        if not sheet:continue
        uid=recognition_identity(sheet['id'],'iso-weld-neck-plate-v1',association['flange_face'],association['opposite_pipe_dot'])
        if any(f['id']==uid for f in features):continue
        features.append({'id':uid,'kind':'flange','profile':'iso-weld-neck-plate-v1',
            **{k:deepcopy(association[k]) for k in ('bbox','flange_face','opposite_pipe_dot')},
            'source_paths':association['source_path_ids'],'sheet_id':sheet['id'],'source_sha256':sheet['sha256'],
            'source_content_hash':sheet.get('content_hash'),'verification':'proposed'})


def prepare_source_points(project):
    """Idempotently propose actual source anchors; never order or connect them."""
    profile=source_profile()
    sheets={s['id']:s for s in project['sheets']}
    matching={s['page_index']:s for s in project['sheets'] if profile and s['sha256']==profile['source_sha256']}
    if matching:
        _profile_materials(project,profile,matching)
        _profile_flanges(project,profile,matching)
    observations=[]
    for feature in project.get('automation',{}).get('feature_proposals',[]):
        sheet=sheets.get(feature['sheet_id'])
        if not sheet or feature['source_sha256']!=sheet['sha256']:continue
        for role in ('flange_face','opposite_pipe_dot'):
            anchor=feature[role]
            observations.append({'id':identity(feature['id'],role),'sheet_id':sheet['id'],'kind':'flange',
                'anchor':anchor,'bbox':[max(0,anchor[0]-5),max(0,anchor[1]-5),min(sheet['width'],anchor[0]+5),min(sheet['height'],anchor[1]+5)],
                'evidence':f"Source geometry {feature['profile']}: inspect {role.replace('_',' ')}; material, topology and engineering station are unconfirmed.",
                'source_feature_id':feature['id'],'source_feature_role':role})
            if matching and sheet['sha256']==profile['source_sha256']:
                association=next((a for a in profile.get('flange_material_associations',[]) if a['page_index']==sheet['page_index'] and
                    a['flange_face']==feature['flange_face'] and a['opposite_pipe_dot']==feature['opposite_pipe_dot']),None)
                if association:observations[-1].update(material_item_no=association['material_item_no'],occurrence=association['occurrence'],
                    port=role,evidence=association['evidence'],source_path_ids=association['source_path_ids'])
    if profile:
        for original in profile.get('observations',[]):
            sheet=matching.get(original['page_index'])
            if sheet:
                observed={**deepcopy(original),'sheet_id':sheet['id']}
                shared=observed.get('shares_flange_face')
                if shared:
                    face=next((o for o in observations if o.get('source_feature_role')=='flange_face' and
                        sheets[o['sheet_id']]['page_index']==shared['page_index'] and o['anchor']==shared['anchor']),None)
                    if face:observed['shares_observation_id']=face['id']
                observations.append(observed)
    if not observations:raise ValueError('No source-bound visual interface evidence is available. Process the drawing first; no positions were fabricated.')
    tombstones=set(project.get('automation_tombstones',{}).get('node_ids',[]))
    nodes={n['id']:n for n in project['nodes']};created=[];observation_nodes={}
    serial=max([int(n.get('review_label','P0')[1:]) for n in project['nodes'] if n.get('review_label','')[1:].isdigit()] or [0])
    for observation in observations:
        sheet=sheets[observation['sheet_id']];anchor=observation['anchor'];bbox=observation['bbox']
        if not (len(anchor)==2 and len(bbox)==4 and 0<=bbox[0]<=anchor[0]<=bbox[2]<=sheet['width'] and 0<=bbox[1]<=anchor[1]<=bbox[3]<=sheet['height']):
            raise ValueError('Source observation is outside its actual page or evidence bounds.')
        uid=identity(project['id'],'source-review-point',sheet['sha256'],observation['id'])
        if uid in nodes:
            observation_nodes[observation['id']]=nodes[uid];continue
        if uid in tombstones:continue
        reference=(observation.get('source_feature_id'),observation.get('source_feature_role'))
        existing=next((n for n in project['nodes'] if reference[0] and (
            (n.get('source_feature_id'),n.get('source_feature_role'))==reference or
            any((v['id'],v['role'])==reference for v in n.get('source_feature_links',[])))),None)
        if existing:
            observation_nodes[observation['id']]=existing;continue
        # Source aliases are explicit observations, never proximity-based merges.
        shared=observation.get('shares_observation_id')
        if shared:
            target=observation_nodes.get(shared)
            if target:
                observation_nodes[observation['id']]=target;continue
            # An alias of a deleted interface must not recreate that interface
            # under a new observation UUID.
            continue
        serial+=1
        if len(project['nodes'])>=2000:raise ValueError('The source point allowance is exhausted; retain the remaining interfaces as explicit exceptions in a separate review project.')
        node={'id':uid,'number':None,'review_label':f'P{serial:03d}','line_id':sheet['line_id'],
            'route':None,'order':None,'takeoff_id':None,'topology_state':'UNASSIGNED','kind':observation['kind'],
            'station_mm':None,'dimension_input':'','evidence':observation['evidence'],
            'origin':'source-review-profile','verification':'proposed','reasons':['TOPOLOGY_UNASSIGNED','UNVERIFIED_DIMENSION','SOURCE_LOCATION_REVIEW_REQUIRED'],
            'source_review_reasons':[],
            'support_gap_mm':None,'instances':[{'sheet_id':sheet['id'],'anchor':list(anchor),
                'bubble':[min(sheet['width']-18,anchor[0]+32),max(18,anchor[1]-32)]}],
            'source_observation':{**deepcopy(observation),'source_sha256':sheet['sha256'],
                'content_hash':sheet.get('content_hash'),'verification':'proposed','coordinate_space':'UNROTATED_PDF_POINTS_ONLY'}}
        for key in ('source_feature_id','source_feature_role'):
            if observation.get(key):node[key]=observation[key]
        project['nodes'].append(node);nodes[uid]=node;created.append(uid);observation_nodes[observation['id']]=node
    model=prepare(project)
    # A source note may suggest a requirement association; it does not approve it.
    by_observation={**{n.get('source_observation',{}).get('id'):n for n in project['nodes'] if n.get('source_observation')},**observation_nodes}
    for observation in observations:
        if not observation.get('material_item_no') or not observation.get('port'):continue
        sheet=sheets[observation['sheet_id']]
        node=by_observation.get(observation.get('shares_observation_id') or observation['id'])
        if not node:continue
        for component in model['components']:
            if (component['sheet_id']!=sheet['id'] or component['item_no']!=str(observation['material_item_no']) or
                component['occurrence']!=observation.get('occurrence',1) or component.get('verification')=='reviewed'):continue
            key=observation['port'];policy=POLICIES[component['kind']]
            if key not in policy['ports'] or component['ports'].get(key):continue
            kind=policy['proof'][policy['ports'].index(key)]
            component['ports'][key]={'point_id':node['id'],'proof':{'kind':kind,'sheet_id':sheet['id'],
                'source_sha256':sheet['sha256'],'content_hash':sheet.get('content_hash'),
                'bbox':deepcopy(observation['bbox']),'evidence':observation['evidence'],'verification':'proposed',
                'source_observation_id':observation['id']}}
    project.setdefault('source_review',{}).update(profile_source_sha256=profile['source_sha256'] if matching else None,
        prepared=True,point_ids=sorted(n['id'] for n in project['nodes'] if n.get('source_observation')),
        source_observation_count=len(observations),observation_points={k:v['id'] for k,v in observation_nodes.items()},engineering_approved=False)
    if matching:
        exceptions=[]
        for entry in profile.get('exceptions',[]):
            sheet=matching.get(entry['page_index'])
            if not sheet:continue
            material=next((m for m in project['materials'] if m['sheet_id']==sheet['id'] and m['item_no']==str(entry.get('material_item_no'))),None)
            if entry['code']=='SOURCE_INVENTORY_METADATA_CORRECTION_REQUIRED' and material and material.get('quantity_unit')=='count' and material.get('quantity')==2:continue
            exceptions.append({**deepcopy(entry),'id':identity(project['id'],entry['id']),
                'sheet_id':sheet['id'],'source_sha256':sheet['sha256'],'material_id':material['id'] if material else None,
                'color':'blue','severity':'critical','status':'REVIEW_REQUIRED','message':entry['evidence']})
        project['source_review']['exceptions']=exceptions
    prepare(project)
    from packages.engineering import refresh_source_locations
    refresh_source_locations(project)
    return created
