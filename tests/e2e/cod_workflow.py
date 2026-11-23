"""Review exact source-line COD without guessing route station or bend radius."""
import io
from pathlib import Path
import fitz
from openpyxl import load_workbook
from playwright.sync_api import expect


def exercise_cod(page,context,base):
    p=context.request.post(base+'/api/v1/projects',data={'title':'SOFTWARE ONLY constrained bend COD','line_id':'COD-QA-001'}).json()
    project=base+'/api/v1/projects/'+p['id']
    with fitz.open() as doc:
        s=doc.new_page(width=600,height=500)
        for y,text in [(35,'SYNTHETIC SOFTWARE TEST ONLY - GRAPHIC SCALE IS NOT PHYSICAL'),
            (60,'Convention: theoretical COD is intersection of the two straight centreline legs.'),
            (330,'A: E 0 mm, N 0 mm, EL 0 mm. B: E 100 mm, N 0 mm, EL 0 mm.'),
            (350,'C: E 200 mm, N 100 mm, EL 0 mm. D: E 200 mm, N 200 mm, EL 0 mm.'),
            (380,'Route station, bend radius and operating properties: UNKNOWN.')]:s.insert_text((25,y),text,fontsize=8)
        raw=doc.tobytes()
    r=context.request.post(project+'/sources?version=1',multipart={'file':{'name':'synthetic-cod.pdf','mimeType':'application/pdf','buffer':raw}})
    assert r.ok,r.text();p=r.json()
    for order in range(5):
        r=context.request.post(project+'/nodes',data={'version':p['version'],'line_id':p['line_id'],'route':'main','order':order,
            'kind':'elbow' if order==2 else 'endpoint','dimension':'','evidence':'SYNTHETIC station unknown; engineering coordinates use independent source table.',
            'instances':[{'sheet_id':p['sheets'][0]['id'],'anchor':[60+order*90,200],'bubble':[60+order*90,150]}]})
        assert r.ok,r.text();p=r.json()
    r=context.request.post(project+'/materials',data={'version':p['version'],'sheet_id':p['sheets'][0]['id'],'item_no':'1','family':'elbow',
        'description':'SYNTHETIC elbow','size':'8','quantity':1,'observed':0,'evidence':'SYNTHETIC component at theoretical source centreline intersection'})
    assert r.ok,r.text();p=r.json()
    for index,point in [(0,[0,0,0]),(1,[100,0,0]),(3,[200,100,0]),(4,[200,200,0])]:
        for axis,value in zip(('X','Y','Z'),point):
            r=context.request.post(project+'/physical-model/dimensions',data={'version':p['version'],'kind':'COORDINATE','axis':axis,
                'from_point_id':p['nodes'][index]['id'],'to_point_id':None,'source_text':str(value)+' mm','tolerance_text':'0 mm',
                'sheet_id':p['sheets'][0]['id'],'evidence':'SYNTHETIC independent printed engineering centreline coordinate','confirmed':True})
            assert r.ok,r.text();p=r.json()
    page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
    page.get_by_role('button',name='Component connections',exact=True).click()
    dialog=page.get_by_role('dialog',name='Component connections',exact=True)
    dialog.get_by_label('Theoretical cod',exact=True).select_option(p['nodes'][2]['id'])
    dialog.get_by_label('Engineering dimension convention proving theoretical COD',exact=True).fill('SYNTHETIC source convention explicitly defines theoretical centreline intersection for the two straight legs.')
    dialog.get_by_label('Source convention proves theoretical centreline intersection',exact=True).check()
    dialog.get_by_label('Engineering source and decision',exact=True).fill('SYNTHETIC inspected the source convention and its independent leg dimensions.')
    dialog.get_by_label('Confirm engineering source evidence',exact=True).check()
    dialog.get_by_role('button',name='Save source connections',exact=True).click()
    expect(dialog).to_have_count(0)
    page.get_by_role('button',name='Review bend COD',exact=True).click()
    dialog=page.get_by_role('dialog',name='Review theoretical bend COD',exact=True)
    expect(dialog).to_contain_text('COD PROPOSED');expect(dialog).to_contain_text('X: 200 mm')
    dialog.get_by_label('Engineering source and decision',exact=True).fill('SYNTHETIC exact physical-leg intersection proved by source constraints, no paper measurements.')
    dialog.get_by_label('Confirm engineering source evidence',exact=True).check()
    dialog.get_by_role('button',name='Accept proved COD coordinates',exact=True).click()
    expect(dialog).to_have_count(0)
    page.get_by_role('tab',name='Bend COD',exact=True).click()
    expect(page.locator('.results-grid tbody')).to_contain_text('COD_ACCEPTED')
    page.get_by_role('button',name='Accept solved XYZ',exact=True).click()
    dialog=page.get_by_role('dialog',name='Accept solved engineering vectors',exact=True)
    dialog.get_by_label('Engineering source and decision',exact=True).fill('SYNTHETIC accepted solved engineering XYZ; route stations, radius and pipe properties remain unknown.')
    dialog.get_by_label('Confirm engineering source evidence',exact=True).check()
    dialog.get_by_role('button',name='Accept engineering vectors',exact=True).click()
    expect(dialog).to_have_count(0)
    p=context.request.get(project).json()
    assert len(p['analysis_model']['elements'])==4 and all(n['station_mm'] is None for n in p['nodes'])
    with page.expect_download() as download:page.get_by_role('link',name='Export Excel (.xlsx)',exact=True).click()
    book=load_workbook(io.BytesIO(Path(download.value.path()).read_bytes()),read_only=True,data_only=True)
    assert book['Bend COD']['C6'].value==200 and book['Bend COD']['F6'].value is None and book['Bend COD']['G6'].value is None
    assert book['CAESAR input']['E6'].value==100 and book['CAESAR input']['N6'].value is None
    assert all(row[4] is None for row in book['Nodes'].iter_rows(min_row=6,max_row=10,values_only=True));book.close()
    page.screenshot(path='/tmp/caesar-screens/proved-bend-cod.png',full_page=True)
    print('PASS: confirmed source COD convention, exact constrained leg intersection, explicit XYZ acceptance, retained unknown stations/radius/properties and shared numeric website/Excel output.',flush=True)
