"""Source-labelled software fixture; never the missing 1010 golden model."""
import io
from pathlib import Path
import time
import fitz
from openpyxl import load_workbook
from playwright.sync_api import expect


def exercise_continuations(page,context,base):
    p=context.request.post(base+'/api/v1/projects',data={'title':'SOFTWARE ONLY independent continuation coordinates','line_id':'CONTINUATION-QA-001'}).json()
    project=base+'/api/v1/projects/'+p['id']
    with fitz.open() as doc:
        for index in range(2):
            source=doc.new_page(width=600,height=500)
            for y,text in [(50,'SYNTHETIC SOFTWARE TEST ONLY'),(75,f'SHEET {index+1} OF 2'),
                    (100,'CONT. ON SHEET 2' if index==0 else 'CONT. FROM SHEET 1'),
                    (160,'E 1000 mm'),(180,'S 500 mm'),(200,'EL 300 mm'),(240,'STATION 100 mm')]:
                source.insert_text((60,y),text,fontsize=10)
        raw=doc.tobytes()
    result=context.request.post(project+'/intake?version=1',data=raw,headers={'Content-Type':'application/pdf','X-Filename':'synthetic-continuations.pdf'})
    assert result.status==202,result.text()
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        run=context.request.get(project+'/pipeline').json()['runs'][0]
        if run['state']=='DONE':break
        assert run['state'] not in ('FAILED','CANCELLED','SUPERSEDED'),run
        page.wait_for_timeout(500)
    else:raise AssertionError('Synthetic continuation intake did not finish')
    p=context.request.get(project).json()
    assert len(p['automation']['continuation_candidates'])==2
    assert len(p['automation']['continuation_pairs'])==1
    for index,s in enumerate(p['sheets']):
        r=context.request.patch(project+'/sheets/'+s['id'],data={'version':p['version'],'printed_id':f'SHEET {index+1} OF 2','line_id':p['line_id'],'axis':None,'table':None,'confirm_identity':True})
        assert r.ok,r.text();p=r.json()
    for index,s in enumerate(p['sheets']):
        r=context.request.post(project+'/nodes',data={'version':p['version'],'line_id':p['line_id'],'route':'main','order':index,
            'kind':'continuation','dimension':'100 mm','evidence':'SYNTHETIC explicit printed source station',
            'instances':[{'sheet_id':s['id'],'anchor':[110,275],'bubble':[150,275]}]})
        assert r.ok,r.text();p=r.json()
    left,right=[n['id'] for n in p['nodes']]
    page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
    for index,point in enumerate((left,right)):
        for axis,value in [('X','E 1000 mm'),('Y','S 500 mm'),('Z','EL 300 mm')]:
            page.get_by_role('button',name='Add source dimension',exact=True).click()
            dialog=page.get_by_role('dialog',name='Add source dimension',exact=True)
            dialog.get_by_label('Constraint type',exact=True).select_option('COORDINATE')
            dialog.get_by_label('Engineering axis',exact=True).select_option(axis)
            dialog.get_by_label('From point / coordinate point',exact=True).select_option(point)
            dialog.get_by_label('Original signed source dimension',exact=True).fill(value)
            dialog.get_by_label('Source drawing page',exact=True).select_option(p['sheets'][index]['id'])
            dialog.get_by_label('Engineering source and decision',exact=True).fill('SYNTHETIC independently inspected printed coordinate on this source sheet.')
            dialog.get_by_role('checkbox').check()
            dialog.get_by_role('button',name='Save source dimension',exact=True).click()
            expect(dialog).to_have_count(0)
    report=context.request.get(project+'/continuations').json();candidates=report['candidates']
    page.get_by_role('button',name='Review continuation',exact=True).click()
    dialog=page.get_by_role('dialog',name='Compare continuation depictions',exact=True)
    dialog.get_by_label('Source point',exact=True).select_option(left)
    dialog.get_by_label('Other sheet point',exact=True).select_option(right)
    dialog.get_by_label('Source nominal pipe size',exact=True).fill('8 in')
    dialog.get_by_label('Other nominal pipe size',exact=True).fill('8')
    for key,index in [('Printed reference for source point',0),('Printed reference for other point',1)]:
        cid=next(c['id'] for c in candidates if c['sheet_id']==p['sheets'][index]['id'])
        dialog.get_by_label(key,exact=True).select_option(cid)
    dialog.get_by_label('Connection decision',exact=True).select_option('ACCEPT_IDENTITY')
    dialog.get_by_label('Continuation engineering evidence',exact=True).fill('SYNTHETIC same nominal size, independent identical source coordinates and inspected common interface/topology.')
    dialog.get_by_label('Confirm continuation interface identity and topology',exact=True).check()
    dialog.get_by_role('button',name='Save continuation review',exact=True).click()
    expect(dialog).to_have_count(0)
    p=context.request.get(project).json();assert len(p['nodes'])==1 and len(p['nodes'][0]['instances'])==2
    assert p['nodes'][0]['id']==left and p['point_aliases'][right]==left
    assert context.request.get(project+'/continuations').json()['issues']==[]
    page.get_by_role('tab',name='Continuations',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(3)
    expect(page.locator('.results-grid tbody')).to_contain_text('ACCEPTED')
    with page.expect_download() as download:page.get_by_role('link',name='Export Excel (.xlsx)',exact=True).click()
    book=load_workbook(io.BytesIO(Path(download.value.path()).read_bytes()),read_only=True,data_only=True)
    assert book['Continuations']['F6'].value==1000 and book['Continuations']['H6'].value==0
    assert book['Dimensions'].max_row==11;book.close()
    for decision,state in [('WITHDRAW','WITHDRAWN'),('REVALIDATE','ACCEPTED')]:
        page.locator('.results-grid tbody tr').first.click()
        dialog=page.get_by_role('dialog',name='Review saved continuation',exact=True)
        dialog.get_by_label('Saved connection decision',exact=True).select_option(decision)
        dialog.get_by_label('Continuation engineering evidence',exact=True).fill('SYNTHETIC explicit '+decision+' of independently inspected common-interface source proof.')
        if decision=='REVALIDATE':dialog.get_by_label('Confirm continuation interface identity and topology',exact=True).check()
        dialog.get_by_role('button',name='Save continuation review',exact=True).click()
        expect(dialog).to_have_count(0);expect(page.locator('.results-grid tbody')).to_contain_text(state)
    page.screenshot(path='/tmp/caesar-screens/continuation-review.png',full_page=True)
    page.locator('.sidebar').get_by_role('button',name='Drawing workspace',exact=True).click()
    expect(page.locator('.node-glyph')).to_have_count(1)
    expect(page.locator('.node-glyph text').first).to_have_text('10')
    page.get_by_label('Next sheet',exact=True).click()
    expect(page.locator('.node-glyph')).to_have_count(1)
    expect(page.locator('.node-glyph text').first).to_have_text('10')
    print('PASS: printed reciprocal references, source E/S/EL entry, exact reviewed identity, shared two-sheet number, retained source constraints, numeric Excel and withdraw/revalidate controls.',flush=True)
