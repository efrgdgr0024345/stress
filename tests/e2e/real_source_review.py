"""The exact real PDF has source points and explicit unknowns, not a golden model."""
import io
from pathlib import Path
from openpyxl import load_workbook
from playwright.sync_api import expect
from tests.e2e.real_drawing import wait_for_drawing

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'


def exercise_real_source_review(page,context,base):
    p=context.request.post(base+'/api/v1/projects',data={'title':'1010 real source interface review — software validation','line_id':'8-PG-JE3LN2-1010-FUTURE'}).json()
    project=base+'/api/v1/projects/'+p['id']
    r=context.request.post(project+'/sources?version=1',multipart={'file':{'name':SOURCE.name,'mimeType':'application/pdf','buffer':SOURCE.read_bytes()}})
    assert r.ok,r.text();p=r.json()
    page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
    page.get_by_role('button',name='Locate source interfaces',exact=True).click()
    expect(page.get_by_role('button',name='Refresh source review',exact=True)).to_be_visible(timeout=30000)
    p=context.request.get(project).json()
    assert len(p['nodes'])==47 and all(n['number'] is None and n['station_mm'] is None and n['route'] is None for n in p['nodes'])
    assert p['graph']['edges']==[]
    page.get_by_role('tab',name='Component ports',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(60)
    expect(page.locator('.results-grid tbody')).to_contain_text('UNLOCATED — EXPLICIT EXCEPTION')
    with page.expect_download() as d:page.get_by_role('link',name='Export Excel (.xlsx)',exact=True).click()
    book=load_workbook(io.BytesIO(Path(d.value.path()).read_bytes()),read_only=True,data_only=True)
    assert book['Component ports'].max_row==65 and book['Nodes'].max_row==52
    assert all(row[0] is None and row[4] is None for row in book['Nodes'].iter_rows(min_row=6,values_only=True));book.close()
    page.locator('.sidebar').get_by_role('button',name='Drawing workspace',exact=True).click()
    wait_for_drawing(page,'.paper canvas')
    expect(page.locator('.node-glyph')).to_have_count(sum(i['sheet_id']==p['sheets'][0]['id'] for n in p['nodes'] for i in n['instances']))
    page.locator('.node-glyph .bubble-handle').first.click()
    expect(page.get_by_role('combobox',name='Route',exact=True)).to_have_value('')
    expect(page.get_by_role('spinbutton',name='Route order',exact=True)).to_have_value('')
    expect(page.get_by_label('Along-route station',exact=False)).to_have_value('')
    expect(page.get_by_label('Confirm current source feature and visual anchor',exact=True)).not_to_be_checked()
    page.get_by_label('Dimension source / evidence',exact=True).fill('SOFTWARE VALIDATION of the actual visible flange plate and source anchor only; physical station and route remain unproved.')
    page.get_by_label('Confirm current source feature and visual anchor',exact=True).check()
    with page.expect_response(lambda r: '/nodes/' in r.url and r.request.method=='PATCH') as saved:
        page.get_by_role('button',name='Save point',exact=True).click()
    assert saved.value.ok, saved.value.text()
    expect(page.get_by_role('button',name='Save point',exact=True)).to_be_disabled()
    p=context.request.get(project).json();point=p['nodes'][0]
    assert point['source_observation']['verification']=='reviewed' and point['topology_state']=='UNASSIGNED' and point['number'] is None
    assert p['graph']['edges']==[] and point['station_mm'] is None
    page.reload();wait_for_drawing(page,'.paper canvas')
    expect(page.locator('.node-glyph text').first).to_have_text('P001')
    page.get_by_label('Next sheet',exact=True).click();wait_for_drawing(page,'.paper canvas')
    page.screenshot(path='/tmp/caesar-screens/real-1010-source-review.png',full_page=True)
    print('PASS: exact real source, 47 provisional source points, 60 interface requirements/55 proposed mappings, five unlocated CODs, separate source confirmation, no invented topology/stations/numbers and actual numeric workbook.',flush=True)
