"""Evidence-linked catalog schedules shared by website, XLSX and CSV."""
from packages.catalogs.project_review import catalog_review_report


def tables(project):
    report=catalog_review_report(project)
    sheets={s['id']:s for s in project['sheets']}
    def table(name,columns,rows):
        return {'name':name,'columns':[{'key':key,'label':label,'kind':kind} for key,label,kind in columns],'rows':rows}
    schedules=[]
    for row in report['rows']:
        maker=row['project_manufacturer'];latest=row['latest_review'] or {};source=row.get('source_observation') or {}
        schedules.append({'id':row['material_id'],'material_id':row['material_id'],
            'page':sheets[row['sheet_id']]['page_index']+1,'sheet_id':row['sheet_id'],'item_no':row['item_no'],
            'family':row['family'],'description':row['description'],'size':row['size'],'quantity':row['quantity'],
            'occurrences':row['occurrence_count'],'status':row['status'],'proposal_status':row['proposal_status'],
            **row['values'],'catalog_quality':row['catalog_source_quality'],'manufacturer_status':maker['status'],
            'manufacturer':maker['vendor'],'manufacturer_model':maker['model'],'reason_codes':', '.join(row['reason_codes']),
            'decision':latest.get('decision'),'decision_evidence':latest.get('evidence'),
            'source_sha256':row['source_sha256'],'source_bbox':str(row.get('source_bbox') or source.get('material_row_bbox')),
            'source_context_sha256':row['source_context_sha256'],'source_transcription':source.get('visual_transcription')})
    occurrences=[{**r,'id':r['component_id'],'page':sheets[r['sheet_id']]['page_index']+1,**r['values']}
                 for r in report['occurrences']]
    decisions=[{**r,'state':'CURRENT' if r['current'] else 'STALE OR EARLIER',
                'catalog_context':r.get('catalog_manifest_sha256')} for r in report['reviews']]
    makers=[{**r,'state':'CURRENT' if r['current'] else 'STALE OR EARLIER'} for r in report['manufacturer_reviews']]
    return [
        table('Catalog schedules',[
            ('page','PDF page','number'),('item_no','Source item','text'),('family','Family','text'),
            ('description','Retained source description','text'),('size','Pipe NPS','text'),('quantity','Source count','number'),
            ('occurrences','Physical occurrences','number'),('status','Project catalog state','text'),
            ('weight_n','W_flange / valve weight (N)','decimal'),('half_weight_n','Flange + half bolting total (N)','decimal'),
            ('full_weight_n','Flange + full bolting total (N)','decimal'),('assembly_weight_n','Assembly weight includes bolting (N)','decimal'),
            ('length_mm','Valve length (mm)','decimal'),('catalog_quality','Catalog source quality','text'),
            ('manufacturer_status','Project manufacturer state','text'),('manufacturer','Confirmed project manufacturer','text'),
            ('manufacturer_model','Confirmed project model','text'),('reason_codes','Missing-data reasons','text'),
            ('decision','Latest review decision','text'),('decision_evidence','Review evidence','text'),
            ('source_transcription','Visual source transcription (proposal)','text'),('source_sha256','Source PDF SHA256','text'),
            ('source_bbox','Source row box (PDF points only)','text'),('source_context_sha256','Reviewed source context SHA256','text'),
            ('material_id','Material ID','text'),('sheet_id','Source sheet ID','text')],schedules),
        table('Catalog occurrences',[
            ('page','PDF page','number'),('item_no','Source item','text'),('family','Family','text'),('status','Catalog state','text'),
            ('weight_n','W_flange / valve weight (N)','decimal'),('half_weight_n','Flange + half bolting total (N)','decimal'),
            ('full_weight_n','Flange + full bolting total (N)','decimal'),('length_mm','Valve length (mm)','decimal'),
            ('assembly_weight_n','Assembly weight includes bolting (N)','decimal'),
            ('component_id','Physical occurrence ID','text'),('material_id','Material ID','text'),('sheet_id','Source sheet ID','text')],occurrences),
        table('Catalog decisions',[
            ('decision','Review decision','text'),('reason_code','Reason code','text'),('evidence','Source review evidence','text'),
            ('state','Review state','text'),('reviewed_by','Recorded by','text'),('reviewed_at','Recorded at','text'),
            ('material_id','Material ID','text'),('source_context_sha256','Source context SHA256','text'),
            ('catalog_context','Catalog manifest SHA256','text'),('id','Review ID','text')],decisions),
        table('Manufacturer reviews',[
            ('decision','Project decision','text'),('vendor','Declared manufacturer','text'),('model','Declared model','text'),
            ('evidence','Actual project evidence','text'),('state','Review state','text'),('reviewed_by','Recorded by','text'),
            ('reviewed_at','Recorded at','text'),('material_id','Material ID','text'),
            ('source_context_sha256','Source context SHA256','text'),('id','Review ID','text')],makers),
    ]
