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
    bindings=project.setdefault('source_review',{}).setdefault('material_bindings',{})
    for observed in profile.get('material_observations',[]):
        sheet=matching.get(observed['page_index'])
        if not sheet:continue
        key=sheet['id']+':'+observed['item_no']
        if bindings.get(key) in tombstones:continue
        if any(i.get('material_id') in tombstones and i.get('sheet_id')==sheet['id'] and
            (i.get('evidence_id')==observed.get('evidence_id') or i.get('bbox')==observed.get('source_bbox'))
            for i in project.get('automation',{}).get('issues',[])):continue
        existing=next((m for m in project['materials'] if m['id']==bindings.get(key)),None)
        existing=existing or next((m for m in project['materials'] if m['sheet_id']==sheet['id'] and m['item_no']==observed['item_no']),None)
        if not existing:
            uid=identity(project['id'],'source-review-material',sheet['sha256'],observed['page_index'],observed['item_no'])
            if uid in tombstones:continue
            existing={**deepcopy(observed),'id':uid,'sheet_id':sheet['id'],'origin':'source-review-profile','verification':'proposed','observed':0}
            project['materials'].append(existing)
        elif existing.get('verification')!='reviewed' and existing.get('quantity_unit')=='unresolved' and observed.get('source_review_notes'):
            existing.setdefault('source_review_history',[]).append({k:deepcopy(existing.get(k)) for k in ('size','quantity','quantity_raw','quantity_value','quantity_unit')})
            existing.update({k:deepcopy(observed[k]) for k in ('size','quantity','quantity_raw','quantity_value','quantity_unit','source_review_notes')})
        bindings[key]=existing['id']
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


def _profile_references(project,profile,matching,observation_nodes):
    """Explicit source transcriptions replace incomplete OCR candidates only.

    They never accept an engineering coordinate or identify two depictions as
    one physical point. Each no-proof match receives a visible endpoint reason.
    """
    from packages.engineering.continuations import candidate_matches,create_source_exception
    facts=profile.get('continuation_source_facts',{})
    for observed in facts.get('sheets',[]):
        sheet=matching.get(observed['page_index'])
        if not sheet:continue
        sheet['source_identity_proposal']=deepcopy(observed)
        if not sheet.get('printed_id'):sheet['printed_id']=observed['printed_id_proposal']
        sheet.setdefault('identity_verified',False)
    automation=project.setdefault('automation',{})
    curated=[]
    for observed in facts.get('continuations',[]):
        sheet=matching.get(observed['page_index'])
        point=observation_nodes.get(observed['source_observation_id'])
        if not sheet:continue
        target=observed['target_reference_proposal']
        source_text=next((o['callout_tag'] for o in profile['observations'] if o['id']==observed['source_observation_id']),target['source_text'])
        candidate={'id':identity(sheet['id'],'source-profile-continuation',observed['source_observation_id']),
            'sheet_id':sheet['id'],'line_id':sheet['line_id'],'source_sha256':sheet['sha256'],
            'source_content_hash':sheet.get('content_hash'),'source_text':source_text,
            'bbox':deepcopy(observed['source_reference_bbox']),'anchor':deepcopy(observed['graphic_anchor']),
            'point_id':point['id'] if point else None,'source_label':observed['source_label'],
            'source_observation_id':observed['source_observation_id'],
            'target_printed_sheet':target.get('printed_sheet'),'target_line_proposal':target.get('normalized_full_line_id'),
            'target_kind':target['kind'],'verification':'proposed','origin':'source-review-profile',
            'printed_coordinate_proposals':deepcopy(observed['source_coordinate_texts']),
            'source_format':observed['source_coordinate_syntax'],'coordinate_text_bbox':deepcopy(observed['coordinate_text_bbox']),
            'nominal_size_proposal':deepcopy(observed['nominal_pipe_size_proposal']),
            'source_evidence':observed['evidence'],'interface_status':observed['interface_status']}
        curated.append(candidate)
    if not curated:return
    old=automation.get('continuation_candidates',[])
    replaced=[c for c in old if c['source_sha256']==profile['source_sha256'] and c.get('origin')!='source-review-profile']
    if replaced:
        archive=automation.setdefault('retained_raw_continuation_candidates',[])
        ids={c['id'] for c in archive};archive.extend(c for c in replaced if c['id'] not in ids)
    automation['continuation_candidates']=[c for c in old if c['source_sha256']!=profile['source_sha256']]+curated
    automation['continuation_pairs']=candidate_matches(automation['continuation_candidates'],project['sheets'])
    for candidate in curated:
        if candidate['target_kind']=='EXTERNAL_PIPING_LINE':
            reason='MISSING_PEER_IN_PACK';evidence='The source names another full piping line, 1093. No peer source/independent coordinates/interface proof is supplied in this drawing pack; an internal match is rejected and an external endpoint exception retained.'
        elif candidate['target_kind']=='EXTERNAL_EQUIPMENT':
            reason='EQUIPMENT_BOUNDARY';evidence='The source names equipment EDUCTOR rather than a peer piping drawing. No nozzle/peer interface evidence is supplied; a reciprocal piping match is rejected and an equipment endpoint exception retained.'
        else:
            reason='ACCEPTED_XYZ_REQUIRED';evidence='The reciprocal printed references and source coordinate text are review proposals only. Independent XYZ, sheet identity and physical interface/topology are not accepted; the current identity match is rejected pending engineering review. No connection was invented.'
        create_source_exception(project,candidate,reason,evidence)


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
        if uid in project.get('point_aliases',{}):
            target=nodes.get(project['point_aliases'][uid])
            if target:observation_nodes[observation['id']]=target
            continue
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
        _profile_references(project,profile,matching,observation_nodes)
    prepare(project)
    from packages.engineering import refresh_source_locations
    refresh_source_locations(project)
    from packages.physical.source_exceptions import refresh_source_exceptions
    refresh_source_exceptions(project)
    return created


def station_source_proposals(project):
    """Actual witnessed source lengths; no signed direction, datum or station is accepted."""
    from packages.engineering.coordinates import coordinate_value
    profile=source_profile()
    if not profile or not project.get('source_review',{}).get('prepared'):return []
    sheets={s['page_index']:s for s in project['sheets'] if s['sha256']==profile['source_sha256']}
    points={n['id']:n for n in project['nodes']};mapping=project.get('source_review',{}).get('observation_points',{})
    aliases=project.get('point_aliases',{})
    def canonical(uid):
        seen=set()
        while uid in aliases:
            if uid in seen:return None
            seen.add(uid);uid=aliases[uid]
        return uid if uid in points else None
    result=[]
    for observed in profile.get('station_source_facts',{}).get('usable_constraints',[]):
        sheet=sheets.get(observed['page_index'])
        if not sheet:continue
        a=canonical(mapping.get(observed['endpoint_a_observation_id']));b=canonical(mapping.get(observed['endpoint_b_observation_id']))
        try:value=coordinate_value(observed['source_text'],'X',observed['source_format'])['value_mm']
        except ValueError:value=None
        result.append({'id':identity(project['id'],'source-station-proposal',observed['id']),
            'source_label':observed['source_label'],'kind':'DELTA','from_point_id':a,'to_point_id':b,
            'from_label':point_label(points[a]) if a else None,'to_label':point_label(points[b]) if b else None,
            'source_text':observed['source_text'],'source_format':observed['source_format'],'proposed_distance_mm':value,
            'sheet_id':sheet['id'],'source_sha256':sheet['sha256'],'source_content_hash':sheet.get('content_hash'),
            'bbox':deepcopy(observed['bbox']),'source_path_ids':deepcopy(observed['source_path_ids']),
            'distance_basis':'ALONG_CENTRELINE','unsigned_source_length':True,'signed_direction_accepted':False,
            'engineering_approved':False,'station_mm':None,'origin_accepted':False,
            'evidence':observed.get('evidence','Actual printed support gap with traced native dimension witnesses.')+
                ' Native source path IDs: '+', '.join(str(i) for i in observed['source_path_ids'])+
                '. Unsigned source length only; explicitly review selected endpoint direction and route datum before applying stations.'})
    return result
