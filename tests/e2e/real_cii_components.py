"""Actual1010 CII source-data drafts: unknown engineering facts stay unknown."""
from pathlib import Path
from playwright.sync_api import expect

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'
EVIDENCE=('DISPOSABLE SOFTWARE VALIDATION ONLY: the actual source elbow still has no accepted radius, '
          'native bend representation/point bridge or complete engineering geometry. Persist this missing-data draft '
          'with null technical values; do not imply CAESAR import readiness or actual engineering approval.')


def exercise_real_cii_components(page,context,base):
    response=context.request.post(base+'/api/v1/projects',data={
        'title':'1010 CII data drafts — DISPOSABLE SOFTWARE VALIDATION','line_id':'8-PG-JE3LN2-1010-FUTURE'})
    assert response.ok,response.text();p=response.json();project=base+'/api/v1/projects/'+p['id']
    response=context.request.post(project+'/sources?version=1',multipart={
        'file':{'name':SOURCE.name,'mimeType':'application/pdf','buffer':SOURCE.read_bytes()}})
    assert response.ok,response.text();p=response.json()
    response=context.request.post(project+'/physical-model/source-points',data={'version':p['version'],'confirmed':True})
    assert response.ok,response.text();p=response.json()
    initial_nodes=p['nodes'];initial_graph=p['graph']
    response=context.request.get(project+'/cii-components')
    assert response.ok,response.text();report=response.json()
    assert report['native_generation_is_application_qualified'] is False
    bends=[r for r in report['requirements'] if r['kind']=='BEND']
    assert len(bends)==5
    bend=bends[0]
    initial_native=context.request.get(project+'/results').json()['native']
    assert not initial_native['available'] and initial_native['missing']
    page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
    expect(page.get_by_role('button',name='CAESAR neutral (.cii)',exact=True)).to_be_disabled()
    page.get_by_role('button',name='CAESAR component data',exact=True).click()
    dialog=page.get_by_role('dialog',name='CAESAR component source data',exact=True)
    dialog.get_by_label('Native component or restraint',exact=True).select_option(bend['id'])
    expect(dialog.get_by_label('Component data review state',exact=True)).to_have_value('DRAFT')
    expect(dialog).to_contain_text('theoretical elbow COD does not automatically identify the native bend far end')
    for field in report['field_schema']['BEND']:
        caption=field['label']+(f" ({field['unit']})" if field.get('unit') else '')
        expect(dialog.get_by_label(caption,exact=True)).to_have_value('')
    dialog.get_by_label('Component source evidence',exact=True).fill(EVIDENCE)
    dialog.get_by_label('Confirm component data record',exact=True).check()
    with page.expect_response(lambda r:'/cii-components/records' in r.url and r.request.method=='POST') as saved:
        dialog.get_by_role('button',name='Save component data',exact=True).click()
    assert saved.value.ok,saved.value.text()
    expect(dialog.get_by_role('button',name='Save component data',exact=True)).to_be_disabled()
    report=context.request.get(project+'/cii-components').json()
    record=next(r for r in report['records'] if r['component_id']==bend['component_id'])
    assert record['review_state']=='DRAFT' and record['evidence']==EVIDENCE
    assert not record['current'] or record['issues']
    assert set(record['values'])=={field['key'] for field in report['field_schema']['BEND']}
    assert all(value is None for value in record['values'].values())
    dialog.get_by_role('button',name='Close',exact=True).click()
    page.reload()
    page.get_by_role('button',name='CAESAR component data',exact=True).click()
    dialog=page.get_by_role('dialog',name='CAESAR component source data',exact=True)
    dialog.get_by_label('Native component or restraint',exact=True).select_option(bend['id'])
    expect(dialog.get_by_label('Component source evidence',exact=True)).to_have_value(EVIDENCE)
    expect(dialog.get_by_label('Component data review state',exact=True)).to_have_value('DRAFT')
    dialog.get_by_role('button',name='Close',exact=True).click()
    p=context.request.get(project).json()
    assert p['nodes']==initial_nodes and p['graph']==initial_graph
    assert len(p['nodes'])==47 and all(n['station_mm'] is None and n['number'] is None for n in p['nodes'])
    native=context.request.get(project+'/results').json()['native']
    assert not native['available'] and native['missing']
    response=context.request.get(project+'/results/caesar-neutral')
    assert response.status==422,response.text()
    expect(page.get_by_role('button',name='CAESAR neutral (.cii)',exact=True)).to_be_disabled()
    print('PASS: actual1010 CII component editor persists explicitBEND DRAFT/sourceevidence with alltechnicalfieldsnull, noCODfar-end inference, unchanged47sourcepoints/unknownstations, nativeCII remainsblocked422; noengineerfactsinvented.',flush=True)
