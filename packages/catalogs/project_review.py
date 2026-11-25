"""Source-bound project catalog decisions; N/A and catalog quality are not approval."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from packages.catalogs import exact_match,match_value,normalize_record,MATCH_FIELDS
from packages.physical import requirements,component_kind,identity

SCHEMA='project-catalog-review-1'
MAX_REVIEWS=2000
NA_REASONS=('SPECIFICATION_UNCONFIRMED','NO_EXACT_CATALOG_MATCH','CATALOG_FACING_UNSPECIFIED',
    'CATALOG_COMPONENT_TYPE_UNSUPPORTED','API_BORE_UNCONFIRMED','VALVE_MANUFACTURER_DATA_UNAVAILABLE',
    'CATALOG_DATASET_UNAPPROVED','COMPONENT_CLASSIFICATION_UNCONFIRMED','CATALOG_RECORD_INCOMPLETE')
REASON_CODES=NA_REASONS+('SOURCE_SPECIFICATION_AND_DATASET_REVIEWED','REVIEW_REOPENED')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def source_context(project,material):
    sheet=next((s for s in project.get('sheets',[]) if s['id']==material['sheet_id']),{})
    return {'material':{k:deepcopy(material.get(k)) for k in ('id','sheet_id','item_no','family','description','size',
        'quantity','quantity_unit','quantity_raw','quantity_value','source_sha256','source_bbox','evidence_id','connection_profile')},
        'sheet':{k:deepcopy(sheet.get(k)) for k in ('id','sha256','content_hash','line_id','printed_id','identity_verified')}}


def catalog_manifest(versions):
    result=[]
    for version in sorted(versions,key=lambda v:v['id']):
        data=version['data'];records=data.get('records',[])
        actual=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()
        valid=bool(data.get('records_sha256')==actual and not data.get('errors') and
            data.get('units',{}).get('weight_output')=='N' and data.get('units',{}).get('length_output')=='mm' and
            version.get('source_integrity_current',True))
        result.append({'catalog_version_id':version['id'],'catalog_id':version.get('catalog_id'),
            'source_sha256':data.get('source_sha256'),'records_sha256':data.get('records_sha256'),
            'status':data.get('status'),'approval':deepcopy(data.get('approval')),'record_count':len(records),
            'source_filename':data.get('source_filename'),'sheet':data.get('sheet') or data.get('mapping',{}).get('sheet'),
            'units':deepcopy(data.get('units',{})),'integrity_current':valid})
    return result


def _source_current(project,material):
    sheet=next((s for s in project.get('sheets',[]) if s['id']==material['sheet_id']),None)
    return bool(sheet and (not material.get('source_sha256') or material['source_sha256']==sheet.get('sha256')))


def _curated_source(project,material):
    path=Path(__file__).resolve().parents[1]/'physical/profiles/1010-catalog-source.json'
    if not path.is_file():return None
    profile=json.loads(path.read_text());sheet=next((s for s in project.get('sheets',[]) if s['id']==material['sheet_id']),{})
    if sheet.get('sha256')!=profile['source_sha256'] or material.get('source_sha256')!=profile['source_sha256']:return None
    return next((row for row in profile['material_rows'] if row['page_index']==sheet.get('page_index') and
        row['material_item_no']==material['item_no'] and row['retained_material_evidence_id']==material.get('evidence_id') and
        row['family_proposal']==material['family'] and match_value('nps',row['size_text'])==match_value('nps',material.get('size'))),None)


def _specification(project,material):
    from packages.automation.recognize import specifications
    # Re-read the current description/size. An old OCR proposal is not authority
    # after a human material correction, and pipe bore never supplies API bore.
    proposed=specifications(material['description'],material.get('size',''),material['family'])
    observed=_curated_source(project,material)
    from packages.physical.source_review import source_profile
    original=next((m for m in (source_profile() or {}).get('material_observations',[]) if m.get('evidence_id')==material.get('evidence_id')),None)
    if observed and original and material['description']==original['description']:
        # Exact source transcriptions supplement delayed OCR only as proposals.
        # Commodity codes and unproved vendor/model identities are not silently
        # promoted into catalog identifiers.
        for key,value in observed['source_spec_proposal'].items():
            if key in ('family','nps','rating','standard','component_type','facing','end_connection','api_bore') and value is not None:
                proposed[key]=value
    return proposed


def _match_binding(match):
    if not match:return None
    return {k:deepcopy(match.get(k)) for k in ('catalog_version_id','catalog_source_sha256',
        'catalog_records_sha256','catalog_approval','spec','record')}


def _manufacturer_binding(project,material):
    return digest({'source':source_context(project,material),'catalog_match':_match_binding(material.get('catalog_match'))})


def _cached_manifest(project):
    if project.get('catalog_review',{}).get('prepared'):return project['catalog_review'].get('catalog_manifest',[])
    return project.get('catalog_reference_manifest')


def current_project_manufacturer(project,material,versions=None):
    records=[r for r in project.get('project_manufacturer_reviews',[]) if r['material_id']==material['id']]
    latest=records[-1] if records else None
    current=bool(latest and _source_current(project,material) and latest.get('source_context_sha256')==digest(source_context(project,material)) and
        latest.get('binding_sha256')==_manufacturer_binding(project,material))
    if current and material.get('catalog_match'):
        current=_snapshot_current(material['catalog_match'],versions,_cached_manifest(project))
    confirmed=bool(current and latest['decision']=='CONFIRM')
    return {'status':'CONFIRMED' if confirmed else 'STALE' if latest and not current else 'UNCONFIRMED',
        'current':current,'vendor':latest.get('vendor') if confirmed else None,'model':latest.get('model') if confirmed else None,
        'latest_review':{**deepcopy(latest),'is_latest':True,'current':current,'stale':not current} if latest else None,
        'catalog_quality_is_project_confirmation':False}


def manufacturer_confirmed(project,material,versions=None):
    return current_project_manufacturer(project,material,versions)['status']=='CONFIRMED'


def _snapshot_current(match,versions,manifest=None):
    if versions is None:
        if manifest is None:return bool(match.get('catalog_approval') and match.get('catalog_source_sha256') and match.get('catalog_records_sha256'))
        meta=next((v for v in manifest if v['catalog_version_id']==match.get('catalog_version_id')),None)
        return bool(meta and meta['status']=='APPROVED' and meta.get('approval') and meta['integrity_current'] and
            meta['source_sha256']==match.get('catalog_source_sha256') and meta['records_sha256']==match.get('catalog_records_sha256'))
    version=next((v for v in versions if v['id']==match.get('catalog_version_id')),None)
    if not version:return False
    meta=catalog_manifest([version])[0];data=version['data']
    if not meta['integrity_current'] or data.get('status')!='APPROVED' or not data.get('approval'):return False
    if match.get('catalog_source_sha256')!=data.get('source_sha256') or match.get('catalog_records_sha256')!=data.get('records_sha256'):return False
    return any(r==match.get('record') for r in data.get('records',[]))


def record_weight_values(record):
    result={k:None for k in ('weight_n','half_weight_n','full_weight_n','length_mm','assembly_weight_n')}
    if not isinstance(record,dict) or not record:return result
    try:normalized=normalize_record(record)
    except (ValueError,TypeError,ArithmeticError):return result
    # Flange bare and bolted totals have different meanings. An assembly/body
    # scope cannot silently populate the W_flange/W_half/W_full columns.
    if record['family']=='flange':
        scope=normalized.get('weight_scope','').upper()
        if scope=='BARE_FLANGE':result['weight_n']=normalized.get('weight_n')
        elif scope=='ASSEMBLY_INCLUDES_BOLTING':result['assembly_weight_n']=normalized.get('weight_n')
        for key in ('half_weight_n','full_weight_n'):
            if scope=='BARE_FLANGE' or record.get(key) is not None:result[key]=normalized.get(key)
    elif record['family']=='valve':
        result.update(weight_n=normalized.get('weight_n'),length_mm=normalized.get('length_mm'))
    return {k:v if v is not None and Decimal(v)>0 else None for k,v in result.items()}


def _proposal(project,material,versions,manifest):
    spec=_specification(project,material);reasons=[];exact=[];partial=[]
    unclassified=material['family'] not in ('flange','valve')
    if unclassified:return spec,exact,partial,['COMPONENT_CLASSIFICATION_UNCONFIRMED'],'CLASSIFICATION_REQUIRED'
    required=['family','standard','rating','component_type','api_bore' if 'api 6a' in str(spec.get('standard','')).lower() else 'nps']
    required+=['facing' if material['family']=='flange' else 'end_connection']
    if any(not spec.get(k) for k in required):reasons.append('SPECIFICATION_UNCONFIRMED')
    if material['family']=='flange' and 'api 6a' in str(spec.get('standard','')).lower() and not spec.get('api_bore'):
        reasons.append('API_BORE_UNCONFIRMED')
    family_records=0
    metadata={m['catalog_version_id']:m for m in manifest}
    for version in sorted(versions,key=lambda v:v['id']):
        meta=metadata[version['id']];records=[r for r in version['data'].get('records',[]) if r.get('family')==material['family']]
        family_records+=len(records)
        found=exact_match(records,{k:v for k,v in spec.items() if k in MATCH_FIELDS})
        for record in found.get('candidates',[]):
            exact.append({'catalog_version_id':version['id'],'record_id':record['id'],'record':deepcopy(record),
                'quality':record['quality'],'dataset_approved':meta['status']=='APPROVED' and bool(meta['approval']),
                'integrity_current':meta['integrity_current']})
        # These are diagnostics, never a near-match or a numeric source. Keep
        # only the same explicitly printed family/standard/rating and NPS/bore.
        for record in records:
            fields=['family','standard','rating']
            size_key='api_bore' if 'api 6a' in str(spec.get('standard','')).lower() else 'nps'
            if spec.get(size_key):fields.append(size_key)
            if not all(spec.get(k) and match_value(k,record.get(k))==match_value(k,spec[k]) for k in fields):continue
            differences=[k for k in ('component_type','facing' if material['family']=='flange' else 'end_connection')
                if spec.get(k) and match_value(k,record.get(k))!=match_value(k,spec[k])]
            if not spec.get(size_key):differences.append('api_bore' if size_key=='api_bore' else 'nps')
            if not differences:continue
            partial.append({'catalog_version_id':version['id'],'record_id':record['id'],
                'source_row':record.get('source_row'),'source_sheet':record.get('source_sheet'),
                'component_type':record.get('component_type'),'facing':record.get('facing'),
                'api_bore':record.get('api_bore'),'nps':record.get('nps'),'quality':record.get('quality'),
                'differences':differences,'limitations':deepcopy(record.get('limitations',[])),
                'acceptance_allowed':False,'numeric_application_allowed':False})
            if 'facing' in differences and record.get('facing','').upper()=='UNSPECIFIED':reasons.append('CATALOG_FACING_UNSPECIFIED')
            if 'component_type' in differences:reasons.append('CATALOG_COMPONENT_TYPE_UNSUPPORTED')
    if not family_records and material['family']=='valve':reasons.append('VALVE_MANUFACTURER_DATA_UNAVAILABLE')
    approved=[c for c in exact if c['dataset_approved'] and c['integrity_current']]
    if exact and not approved:reasons.append('CATALOG_DATASET_UNAPPROVED')
    if not exact:reasons.append('NO_EXACT_CATALOG_MATCH')
    status='CURRENT_CANDIDATE' if len(approved)==1 else 'AMBIGUOUS_CANDIDATES' if len(approved)>1 else 'DATASET_REVIEW_REQUIRED' if exact else 'UNAVAILABLE'
    return spec,exact,partial[:20],sorted(set(reasons)),status


def catalog_review_report(project,versions=None):
    state=project.get('catalog_review',{})
    manifest=catalog_manifest(versions) if versions is not None else deepcopy(state.get('catalog_manifest',[]));manifest_sha=digest(manifest)
    components=requirements(project)[0];raw=project.get('project_catalog_reviews',[])
    latest={r['material_id']:r for r in raw};rows=[];current_reviews={}
    for material in project.get('materials',[]):
        if material['family'] not in ('flange','valve') and component_kind(material)!='inline_component_unclassified':continue
        context_sha=digest(source_context(project,material))
        cached=next((r for r in state.get('proposals',[]) if r['material_id']==material['id'] and r['source_context_sha256']==context_sha),None)
        if versions is None and cached:
            spec,exact,partial,reasons,proposal_status=(deepcopy(cached[k]) for k in ('source_specification','exact_candidates','partial_candidates','reason_codes','proposal_status'))
        else:spec,exact,partial,reasons,proposal_status=_proposal(project,material,versions or [],manifest)
        review=latest.get(material['id']);current=bool(review and _source_current(project,material) and
            review.get('source_context_sha256')==context_sha and review.get('catalog_manifest_sha256')==manifest_sha)
        match=material.get('catalog_match');accepted=False
        if current and review['decision']=='ACCEPT_EXACT_MATCH':
            accepted=bool(match and review.get('match_sha256')==digest(_match_binding(match)) and _snapshot_current(match,versions,manifest))
            current=accepted
        declared=current and review['decision']=='DECLARE_NA'
        if not _source_current(project,material):status='SOURCE_STALE'
        elif review and not current:status='REVIEW_STALE'
        elif accepted:status='MATCHED_REFERENCE'
        elif declared:status='DECLARED_NA'
        elif current and review['decision']=='REOPEN':status='REOPENED'
        elif match:status='MATCH_REVIEW_REQUIRED'
        else:status='REVIEW_REQUIRED'
        record=match.get('record') if accepted else None
        try:values=record_weight_values(record)
        except ValueError:values=record_weight_values(None);reasons.append('CATALOG_RECORD_INCOMPLETE')
        if accepted:
            keys=('weight_n','half_weight_n','full_weight_n') if material['family']=='flange' else ('weight_n','length_mm')
            if any(values[k] is None for k in keys):reasons.append('CATALOG_RECORD_INCOMPLETE')
        occurrences=[c['id'] for c in components if c['material_id']==material['id']]
        manufacturer=current_project_manufacturer(project,material,versions)
        row={'material_id':material['id'],'sheet_id':material['sheet_id'],'item_no':material['item_no'],
            'family':material['family'],'description':material['description'],'size':material.get('size'),
            'quantity':material.get('quantity'),'occurrence_ids':occurrences,'occurrence_count':len(occurrences),
            'source_sha256':material.get('source_sha256') or next((s.get('sha256') for s in project['sheets'] if s['id']==material['sheet_id']),None),
            'source_bbox':deepcopy(material.get('source_bbox')),'source_context_sha256':context_sha,
            'source_specification':spec,'status':status,'proposal_status':proposal_status,'reason_codes':sorted(set(reasons)),
            'source_observation':deepcopy(_curated_source(project,material)),
            'exact_candidates':exact[:100],'partial_candidates':partial,'values':values,
            'catalog_source_quality':record.get('quality') if record else None,
            'project_manufacturer':manufacturer,'latest_review':{**deepcopy(review),'is_latest':True,'current':current,'stale':not current} if review else None,
            'current':current,'review_complete':accepted or declared,'numeric_complete':accepted and all(values[k] is not None for k in
                (('weight_n','half_weight_n','full_weight_n') if material['family']=='flange' else ('weight_n','length_mm'))),
            'color':'blue' if not accepted or not manufacturer['status']=='CONFIRMED' or reasons else None,
            'engineering_approved':False,'na_is_engineering_approval':False}
        rows.append(row)
        if review:current_reviews[review['id']]=current
    classification_rows=[r for r in rows if r['family'] not in ('flange','valve')]
    rows=[r for r in rows if r['family'] in ('flange','valve')]
    classification_issues=[{'code':'COMPONENT_CLASSIFICATION_UNCONFIRMED','severity':'critical','color':'blue',
        'material_id':r['material_id'],'sheet_id':r['sheet_id'],'source_sha256':r['source_sha256'],
        'message':'Source process ends do not establish whether this item is a valve or instrument. Confirm classification before catalog matching.',
        'engineering_approved':False} for r in classification_rows]
    reviews=[{**deepcopy(r),'is_latest':latest.get(r['material_id'],{}).get('id')==r['id'],
        'current':current_reviews.get(r['id'],False),'stale':not current_reviews.get(r['id'],False)} for r in raw]
    manufacturer_reviews=[]
    for raw_review in project.get('project_manufacturer_reviews',[]):
        row=next((r for r in rows if r['material_id']==raw_review['material_id']),None)
        last=row['project_manufacturer']['latest_review'] if row else None
        current=bool(last and last['id']==raw_review['id'] and last['current'])
        manufacturer_reviews.append({**deepcopy(raw_review),'is_latest':bool(last and last['id']==raw_review['id']),
            'current':current,'stale':not current})
    sheets=[]
    for sheet in project.get('sheets',[]):
        entries=[r for r in rows if r['sheet_id']==sheet['id']]
        sheets.append({'sheet_id':sheet['id'],'rows':entries,'review_complete':all(r['review_complete'] for r in entries),
            'numeric_complete':bool(entries) and all(r['numeric_complete'] for r in entries),'engineering_approved':False})
    occurrences=[{'component_id':uid,'material_id':r['material_id'],'sheet_id':r['sheet_id'],'item_no':r['item_no'],
        'family':r['family'],'status':r['status'],'values':deepcopy(r['values']),'current':r['current'],
        'review_complete':r['review_complete'],'engineering_approved':False} for r in rows for uid in r['occurrence_ids']]
    return {'schema':SCHEMA,'prepared':bool(project.get('catalog_review',{}).get('prepared')),'catalog_manifest':manifest,
        'catalog_manifest_sha256':manifest_sha,'rows':rows,'sheets':sheets,'occurrences':occurrences,
        'reviews':reviews,'manufacturer_reviews':manufacturer_reviews,'reason_codes':list(REASON_CODES),
        'classification_rows':classification_rows,'classification_issues':classification_issues,
        'summary':{'materials':len(rows),'occurrences':len(occurrences),'matched':sum(r['status']=='MATCHED_REFERENCE' for r in rows),
            'declared_na':sum(r['status']=='DECLARED_NA' for r in rows),'review_complete':all(r['review_complete'] for r in rows),
            'numeric_complete':bool(rows) and all(r['numeric_complete'] for r in rows)},'engineering_approved':False}


def prepare_catalog_review(project,versions,reviewer,reviewed_at):
    report=catalog_review_report(project,versions)
    project['catalog_review']={'schema':SCHEMA,'prepared':True,'prepared_by':reviewer,'prepared_at':reviewed_at,
        'catalog_manifest':deepcopy(report['catalog_manifest']),'summary':deepcopy(report['summary']),
        'proposals':[{k:deepcopy(r[k]) for k in ('material_id','source_context_sha256','source_specification','exact_candidates','partial_candidates','reason_codes','proposal_status')} for r in report['rows']]}
    return report


def record_catalog_decision(project,versions,material_id,decision,reason_code,evidence,reviewer,reviewed_at,
                            source_context_sha256,catalog_version_id=None,record_id=None):
    if decision not in ('ACCEPT_EXACT_MATCH','DECLARE_NA','REOPEN'):raise ValueError('Unsupported project catalog decision.')
    if not isinstance(evidence,str) or not 10<=len(evidence.strip())<=3000 or not reviewer or not reviewed_at:
        raise ValueError('Current authenticated source-review evidence is required.')
    if not project.get('catalog_review',{}).get('prepared'):raise ValueError('Prepare the current project catalog review before recording a decision.')
    report=catalog_review_report(project,versions);row=next((r for r in report['rows'] if r['material_id']==material_id),None)
    if not row:raise ValueError('Select a classified flange or valve; source-unclassified items retain their independent blue classification requirement.')
    material=next(m for m in project['materials'] if m['id']==material_id)
    if len(project.get('project_catalog_reviews',[]))>=MAX_REVIEWS:raise ValueError('Project catalog review history allowance reached.')
    if row['source_context_sha256']!=source_context_sha256 or not _source_current(project,material):raise ValueError('The source material context changed; reload and inspect current catalog evidence.')
    if decision=='ACCEPT_EXACT_MATCH':
        if reason_code!='SOURCE_SPECIFICATION_AND_DATASET_REVIEWED':raise ValueError('Use the explicit source/dataset acceptance reason.')
        candidate=next((c for c in row['exact_candidates'] if c['catalog_version_id']==catalog_version_id and c['record_id']==record_id),None)
        if not candidate or not candidate['dataset_approved'] or not candidate['integrity_current']:
            raise ValueError('Select an exact source-specification match from an approved current dataset. Partial diagnostics cannot be accepted.')
        if len([c for c in row['exact_candidates'] if c['dataset_approved'] and c['integrity_current']])!=1:
            raise ValueError('Resolve multiple exact catalog candidates explicitly; none was selected by row or array order.')
        data=next(v['data'] for v in versions if v['id']==catalog_version_id)
        material['catalog_match']={'catalog_version_id':catalog_version_id,'catalog_source_sha256':data['source_sha256'],
            'catalog_records_sha256':data['records_sha256'],'catalog_approval':deepcopy(data['approval']),
            'spec':{k:v for k,v in row['source_specification'].items() if k in MATCH_FIELDS},'record':deepcopy(candidate['record']),
            'status':'ESTIMATED' if candidate['quality']=='ESTIMATED' else 'REFERENCE_ONLY',
            'reason':evidence.strip(),'matched_by':reviewer,'matched_at':reviewed_at,'match_method':SCHEMA}
    elif decision=='DECLARE_NA':
        if reason_code not in NA_REASONS:raise ValueError('Choose a typed reason for unavailable project catalog data.')
    elif reason_code!='REVIEW_REOPENED':raise ValueError('Use the explicit review-reopened reason.')
    if decision!='ACCEPT_EXACT_MATCH':
        if catalog_version_id or record_id:raise ValueError('Only exact-match acceptance may select a dataset record.')
        previous=material.pop('catalog_match',None)
        if previous:material.setdefault('catalog_match_history',[]).append(deepcopy(previous))
    records=project.setdefault('project_catalog_reviews',[])
    record={'id':identity(project['id'],'project-catalog-review',material_id,len(records)+1,reviewed_at),
        'material_id':material_id,'decision':decision,'reason_code':reason_code,'evidence':evidence.strip(),
        'reviewed_by':reviewer,'reviewed_at':reviewed_at,'source_context_sha256':source_context_sha256,
        'catalog_manifest_sha256':report['catalog_manifest_sha256'],'catalog_version_id':catalog_version_id,'record_id':record_id,
        'match_sha256':digest(_match_binding(material.get('catalog_match'))) if decision=='ACCEPT_EXACT_MATCH' else None,
        'engineering_approved':False}
    records.append(record);material['auto_match_disabled']=True
    project['materials_reviewed']=False;project['layout_reviewed']=False
    return deepcopy(record)


def record_manufacturer_decision(project,material_id,decision,vendor,model,evidence,reviewer,reviewed_at,source_context_sha256):
    material=next((m for m in project.get('materials',[]) if m['id']==material_id and m['family'] in ('flange','valve')),None)
    if not material:raise ValueError('Confirm actual manufacturer identity only for a classified flange or valve.')
    if decision not in ('CONFIRM','REOPEN') or not reviewer or not reviewed_at:raise ValueError('An explicit authenticated manufacturer decision is required.')
    if not isinstance(evidence,str) or not 20<=len(evidence.strip())<=3000:raise ValueError('Describe the independent actual project manufacturer/model evidence; catalog quality is not confirmation.')
    if not _source_current(project,material) or digest(source_context(project,material))!=source_context_sha256:raise ValueError('The source material changed; inspect current manufacturer evidence again.')
    if decision=='CONFIRM' and (not isinstance(vendor,str) or not 2<=len(vendor.strip())<=150 or not isinstance(model,str) or not 1<=len(model.strip())<=150):
        raise ValueError('Supply the actual project vendor and model from independently checked engineering evidence.')
    records=project.setdefault('project_manufacturer_reviews',[])
    if len(records)>=MAX_REVIEWS:raise ValueError('Manufacturer review history allowance reached.')
    record={'id':identity(project['id'],'manufacturer-review',material_id,len(records)+1,reviewed_at),
        'material_id':material_id,'decision':decision,'vendor':vendor.strip() if vendor else None,'model':model.strip() if model else None,
        'evidence':evidence.strip(),'reviewed_by':reviewer,'reviewed_at':reviewed_at,'source_context_sha256':source_context_sha256,
        'binding_sha256':_manufacturer_binding(project,material),'engineering_approved':False}
    records.append(record);project['materials_reviewed']=False;project['layout_reviewed']=False
    return deepcopy(record)


def refresh_project_catalog_reviews(project,versions=None):
    """Persist current report facts/reasons, never approve/waive data or alter numbers."""
    prepared=bool(project.get('catalog_review',{}).get('prepared'))
    if versions is not None:project['catalog_reference_manifest']=catalog_manifest(versions)
    for material in project.get('materials',[]):
        if material['family'] not in ('flange','valve'):continue
        maker=current_project_manufacturer(project,material,versions)
        material['project_manufacturer_status']=maker['status']
        match=material.get('catalog_match')
        material['catalog_review_state']={'match_current':bool(match and _source_current(project,material) and
            _snapshot_current(match,versions,_cached_manifest(project))),
            'manufacturer_status':maker['status'],'status':'LEGACY_REFERENCE' if match else 'REVIEW_REQUIRED'}
    if not prepared:return []
    report=catalog_review_report(project,versions);issues=deepcopy(report['classification_issues'])
    for row in report['rows']:
        material=next(m for m in project['materials'] if m['id']==row['material_id'])
        material['project_catalog_review']={k:deepcopy(row[k]) for k in ('status','current','reason_codes','values','source_context_sha256','review_complete','numeric_complete','project_manufacturer')}
        material['catalog_review_state']={**deepcopy(material['project_catalog_review']),
            'match_current':row['status']=='MATCHED_REFERENCE','manufacturer_status':row['project_manufacturer']['status']}
        if row['status']!='MATCHED_REFERENCE':
            code='CATALOG_DATA_DECLARED_NA' if row['status']=='DECLARED_NA' else 'PROJECT_CATALOG_REVIEW_REQUIRED'
            issues.append({'code':code,'severity':'critical','color':'blue','material_id':material['id'],'sheet_id':material['sheet_id'],
                'source_sha256':row['source_sha256'],'evidence':row['latest_review']['evidence'] if row['latest_review'] else None,
                'message':'Catalog data remains unavailable with an explicit source-bound reason; N/A is not engineering approval.' if row['status']=='DECLARED_NA' else 'Review the current exact catalog specification, source limitations and dataset approval.',
                'engineering_approved':False})
        if not row['numeric_complete']:
            issues.append({'code':'CATALOG_NUMERIC_DATA_UNAVAILABLE','severity':'critical','color':'blue','material_id':material['id'],
                'sheet_id':material['sheet_id'],'message':'Required component weight/bolting/length values remain unknown, never zero.','engineering_approved':False})
    project['catalog_review'].update(catalog_manifest=deepcopy(report['catalog_manifest']),summary=deepcopy(report['summary']),
        rows=[{k:deepcopy(r[k]) for k in ('material_id','sheet_id','status','current','values','source_context_sha256','reason_codes','review_complete','numeric_complete')} for r in report['rows']])
    project['catalog_review']['issues']=issues
    project['catalog_review']['proposals']=[{k:deepcopy(r[k]) for k in ('material_id','source_context_sha256','source_specification','exact_candidates','partial_candidates','reason_codes','proposal_status')} for r in report['rows']]
    return issues


refresh_catalog_review=refresh_project_catalog_reviews
