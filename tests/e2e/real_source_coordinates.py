"""Actual printed XYZ review; software declarations never approve live geometry."""
from pathlib import Path
from playwright.sync_api import expect

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'


def exercise_real_source_coordinates(page,context,base):
    response=context.request.post(base+'/api/v1/projects',data={
        'title':'1010 printed XYZ — DISPOSABLE SOFTWARE VALIDATION','line_id':'8-PG-JE3LN2-1010-FUTURE'})
    assert response.ok,response.text();p=response.json();project=base+'/api/v1/projects/'+p['id']
    response=context.request.post(project+'/sources?version=1',multipart={
        'file':{'name':SOURCE.name,'mimeType':'application/pdf','buffer':SOURCE.read_bytes()}})
    assert response.ok,response.text();p=response.json()
    response=context.request.post(project+'/physical-model/source-points',data={'version':p['version'],'confirmed':True})
    assert response.ok,response.text();p=response.json()
    candidate=next(c for c in p['automation']['continuation_candidates'] if c['source_label']=='S1-CONT-SHEET2')
    page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
    page.get_by_role('button',name='Review printed XYZ',exact=True).click()
    dialog=page.get_by_role('dialog',name='Review printed source coordinates',exact=True)
    dialog.get_by_label('Printed coordinate reference',exact=True).select_option(candidate['id'])
    expect(dialog).to_contain_text('SOURCE INSPECTION REQUIRED',ignore_case=True)
    expect(dialog.get_by_role('button',name='Accept printed XYZ coordinates',exact=True)).to_be_disabled()
    dialog.get_by_role('button',name='Cancel',exact=True).click()
    node=next(n for n in p['nodes'] if n['id']==candidate['point_id'])
    response=context.request.patch(project+'/nodes/'+node['id'],data={
        'version':p['version'],'line_id':node['line_id'],'kind':node['kind'],'topology_state':'UNASSIGNED',
        'route':None,'order':None,'dimension':'','instances':node['instances'],
        'source_location_confirmed':True,'source_location_sheet_id':candidate['sheet_id'],
        'evidence':'DISPOSABLE SOFTWARE VALIDATION of the actual printed source coordinate block and leader. No station or engineering approval.'})
    assert response.ok,response.text();p=response.json();page.reload()
    page.get_by_role('button',name='Review printed XYZ',exact=True).click()
    dialog=page.get_by_role('dialog',name='Review printed source coordinates',exact=True)
    dialog.get_by_label('Printed coordinate reference',exact=True).select_option(candidate['id'])
    expect(dialog).to_contain_text('41255.95')
    expect(dialog).to_contain_text('-95361.125')
    expect(dialog).to_contain_text('11550.65')
    dialog.get_by_label('Declared coordinate tolerance',exact=True).fill('0 mm')
    dialog.get_by_label('Coordinate source evidence',exact=True).fill(
        'DISPOSABLE SOFTWARE VALIDATION of actual E135ft4-1/4in, S312ft10-3/8in and EL37ft10-3/4in source. No station or lead approval.')
    dialog.get_by_label('Confirm printed XYZ source evidence',exact=True).check()
    with page.expect_response(lambda r:'/source-coordinates/' in r.url and r.request.method=='POST') as saved:
        dialog.get_by_role('button',name='Accept printed XYZ coordinates',exact=True).click()
    assert saved.value.ok,saved.value.text()
    expect(dialog).not_to_be_visible()
    p=context.request.get(project).json()
    assert all(n['station_mm'] is None and n['number'] is None for n in p['nodes'])
    assert p['graph']['edges']==[]
    page.get_by_role('tab',name='Printed coordinates',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(12)
    expect(page.locator('.results-grid tbody')).to_contain_text('ACCEPTED')
    page.screenshot(path='/tmp/caesar-screens/real-1010-printed-coordinates.png',full_page=True)
    print('PASS: exact-source printed XYZ UI, current independent source inspection, explicit tolerance, numeric shared table; no invented station, topology or engineering approval.',flush=True)
