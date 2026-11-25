"""Typed native inputs and explicit unsupported requirements, never guessed values."""
from decimal import Decimal,InvalidOperation
from packages.workbooks.cii_components import component_report


def tables(project):
    report=component_report(project)
    def table(name,columns,rows):
        return {'name':name,'columns':[{'key':key,'label':label,'kind':kind} for key,label,kind in columns],'rows':rows}
    requirements=[{**r,'point_ids':', '.join(r['point_ids']),'missing':', '.join(r['missing']),
                   'state':r['record']['review_state'] if r.get('record') else 'INPUT REQUIRED'} for r in report['requirements']]
    values=[]
    for record in report['records']:
        reasons=', '.join(sorted({i['code'] for i in record['issues']}))
        for field in report['field_schema'][record['kind']]:
            raw=record['values'].get(field['key']);number=None
            if field['type']=='decimal' and raw is not None and raw!='':
                try:
                    parsed=Decimal(str(raw))
                    positive=field['key'] in ('weight_n','radius_mm','stiffness_n_per_mm') or field['key'].endswith(('_sif','_index'))
                    if parsed.is_finite() and parsed.copy_abs()<=Decimal('1000000000000') and (not positive or parsed>0):number=str(parsed)
                except InvalidOperation:pass
            values.append({'id':record['id']+':'+field['key'],'record_id':record['id'],'kind':record['kind'],
                'field':field['key'],'label':field['label'],'unit':field.get('unit'),'numeric_value':number,
                'raw_value':str(raw) if raw is not None else None,'state':record['review_state'],
                'proof_state':'CURRENT' if record['current'] else 'STALE','reasons':reasons,
                'component_id':record.get('component_id'),'point_id':record.get('point_id'),
                'element_id':record.get('element_id'),'source_sheet_id':record.get('source_sheet_id'),
                'evidence':record['evidence'],'source_context_sha256':record['source_context_sha256']})
    return [
        table('Native requirements',[
            ('kind','Native component family','text'),('item_no','Source item','text'),('occurrence','Occurrence','number'),
            ('state','Input review state','text'),('missing','Missing native data','text'),
            ('component_id','Physical component ID','text'),('point_ids','Physical point IDs','text'),('sheet_id','Source sheet ID','text')],requirements),
        table('Native component inputs',[
            ('kind','Native family','text'),('label','Input field','text'),('numeric_value','Parsed draft numeric value','decimal'),
            ('raw_value','Original entered value','text'),('unit','Declared unit','text'),('state','Review state','text'),
            ('proof_state','Source proof state','text'),('reasons','Generation blockers','text'),('evidence','Source evidence','text'),
            ('record_id','Native input record ID','text'),('component_id','Physical component ID','text'),
            ('point_id','Physical point ID','text'),('element_id','Carrier element ID','text'),
            ('source_sheet_id','Source sheet ID','text'),('source_context_sha256','Source context SHA256','text')],values),
    ]
