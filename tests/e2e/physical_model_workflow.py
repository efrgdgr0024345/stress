"""Browser edits physical interfaces and source dimensions in the workbook."""
from pathlib import Path
import io
import fitz
from openpyxl import load_workbook
from playwright.sync_api import expect


def exercise_physical_model(page,context,base):
    p=context.request.post(base+'/api/v1/projects',data={'title':'SOFTWARE ONLY physical model test','line_id':'PHYSICAL-QA-001'}).json()
    project=base+'/api/v1/projects/'+p['id']
    with fitz.open() as doc:
        source=doc.new_page(width=600,height=500)
        source.insert_text((50,90),'SYNTHETIC SOFTWARE TEST ONLY - FLANGE FACE AND OPPOSITE DOT')
        source.insert_text((50,120),'Source fixture: accepted stations 0 mm and 100 mm; DX 100 mm, DY 0 mm, DZ 0 mm.')
        raw=doc.tobytes()
    response=context.request.post(project+'/sources?version=1',multipart={'file':{'name':'physical-software-only.pdf','mimeType':'application/pdf','buffer':raw}})
    assert response.ok,response.text();p=response.json()
    for order in range(2):
        r=context.request.post(project+'/nodes',data={'version':p['version'],'line_id':p['line_id'],'route':'main','order':order,'kind':'endpoint','dimension':f'{100*order} mm','evidence':'SOFTWARE ONLY explicit synthetic station source','instances':[{'sheet_id':p['sheets'][0]['id'],'anchor':[70+100*order,180],'bubble':[70+100*order,140]}]})
        assert r.ok,r.text();p=r.json()
    r=context.request.post(project+'/materials',data={'version':p['version'],'sheet_id':p['sheets'][0]['id'],'item_no':'1','family':'flange','description':'SYNTHETIC WN flange','size':'8','quantity':1,'observed':0,'evidence':'SOFTWARE ONLY component fixture'})
    assert r.ok,r.text();p=r.json()
    page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
    expect(page.get_by_role('heading',name='Results workbook.',exact=True)).to_be_visible()
    page.get_by_role('tab',name='Component ports',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(2)
    page.locator('.results-grid tbody tr').first.click()
    dialog=page.get_by_role('dialog',name='Component connections',exact=True)
    dialog.get_by_label('Flange face',exact=True).select_option(p['nodes'][0]['id'])
    dialog.get_by_label('Opposite pipe dot',exact=True).select_option(p['nodes'][1]['id'])
    dialog.get_by_label('Engineering source and decision',exact=True).fill('SOFTWARE ONLY inspected synthetic face and opposite pipe black dot.')
    dialog.get_by_role('checkbox').check();dialog.get_by_role('button',name='Save source connections',exact=True).click()
    expect(dialog).to_have_count(0)
    expect(page.locator('.results-grid tbody')).to_contain_text('SOURCE ASSOCIATION REVIEWED')
    for axis,value in [('X','100 mm'),('Y','0 mm'),('Z','0 mm')]:
        page.get_by_role('button',name='Add source dimension',exact=True).click()
        dialog=page.get_by_role('dialog',name='Add source dimension',exact=True)
        dialog.get_by_label('Engineering axis',exact=True).select_option(axis)
        dialog.get_by_label('Original signed source dimension',exact=True).fill(value)
        dialog.get_by_label('Engineering source and decision',exact=True).fill('SOFTWARE ONLY accepted signed source axis and explicit zero components.')
        dialog.get_by_role('checkbox').check();dialog.get_by_role('button',name='Save source dimension',exact=True).click()
        expect(dialog).to_have_count(0)
    page.get_by_role('tab',name='Dimensions',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(3)
    page.get_by_role('button',name='Accept solved XYZ',exact=True).click()
    dialog=page.get_by_role('dialog',name='Accept solved engineering vectors',exact=True)
    dialog.get_by_label('Engineering source and decision',exact=True).fill('SOFTWARE ONLY independently checked exact signed source vectors.')
    dialog.get_by_role('checkbox').check();dialog.get_by_role('button',name='Accept engineering vectors',exact=True).click()
    expect(dialog).to_have_count(0)
    page.get_by_role('tab',name='CAESAR input',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(1)
    p=context.request.get(project).json()
    assert p['analysis_model']['elements'][0]['dx_mm']=='100'
    assert len(p['nodes'])==2 and p['materials'][0]['observed']==1
    with page.expect_download() as download:page.get_by_role('link',name='Export Excel (.xlsx)',exact=True).click()
    book=load_workbook(io.BytesIO(Path(download.value.path()).read_bytes()))
    assert {'Component ports','Dimensions','Coordinates'}<=set(book.sheetnames)
    assert book['Component ports'].max_row==7
    assert book['Dimensions']['F6'].value==100 and book['Dimensions']['E6'].value=='100 mm'
    assert book['Coordinates']['D6'].value is None and book['Coordinates']['G6'].value=='RELATIVE_ONLY'
    assert book['Dimensions'].freeze_panes=='C6';book.close()
    page.screenshot(path='/tmp/caesar-screens/physical-model-workbook.png',full_page=True)
    print('PASS: source-bound physical interfaces, signed XYZ entry/acceptance, retained stations and numeric shared website/XLSX model sheets.',flush=True)
