"""Real drawing symbol proposals can seed editable points without fake distances."""
import io
from pathlib import Path
import time
from openpyxl import load_workbook
from playwright.sync_api import expect


def exercise_source_features(page,context,base):
    source=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'
    p=context.request.post(base+'/api/v1/projects',data={'title':'SOFTWARE ONLY real source flange proposals','line_id':'8-PG-JE3LN2-1010-FUTURE'}).json()
    project=base+'/api/v1/projects/'+p['id']
    result=context.request.post(project+'/intake?version=1',data=source.read_bytes(),headers={'Content-Type':'application/pdf','X-Filename':source.name})
    assert result.status==202,result.text()
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        report=context.request.get(project+'/pipeline').json()['runs'][0]
        if report['state']=='DONE':break
        assert report['state'] not in ('FAILED','CANCELLED','SUPERSEDED'),report
        page.wait_for_timeout(500)
    else:raise AssertionError('Real source recognition did not complete')
    page.goto(base+f"/?project={p['id']}&view=workspace",wait_until='domcontentloaded')
    expect(page.locator('.source-feature')).to_have_count(4)
    expect(page.locator('[data-feature-role]')).to_have_count(8)
    page.get_by_role('button',name='Detected features',exact=True).click()
    expect(page.locator('.source-feature-card')).to_have_count(4)
    page.screenshot(path='/tmp/caesar-screens/real-flange-proposals.png',full_page=True)
    page.get_by_role('button',name='Inspect face',exact=True).first.click()
    expect(page.get_by_role('heading',name='New physical point',exact=True)).to_be_visible()
    expect(page.get_by_label('Dimension source / evidence',exact=True)).to_have_value(__import__('re').compile('Source feature .+/flange_face'))
    page.get_by_role('button',name='Save point',exact=True).click()
    expect(page.get_by_role('heading',name='Physical point',exact=True)).to_be_visible()
    # Selected-point -> new candidate exercises preservation of the new draft.
    page.get_by_role('button',name='Detected features',exact=True).click()
    page.get_by_role('button',name='Inspect pipe dot',exact=True).first.click()
    expect(page.get_by_role('heading',name='New physical point',exact=True)).to_be_visible()
    page.get_by_role('button',name='Save point',exact=True).click()
    expect(page.get_by_role('heading',name='Physical point',exact=True)).to_be_visible()
    p=context.request.get(project).json();assert len(p['nodes'])==2,p
    assert all(n['station_mm'] is None and 'UNVERIFIED_DIMENSION' in n['reasons'] for n in p['nodes'])
    assert p['nodes'][0]['instances'][0]['anchor']!=p['nodes'][1]['instances'][0]['anchor']
    page.get_by_role('button',name='Detected features',exact=True).click()
    page.get_by_role('button',name='Inspect face',exact=True).first.click()
    expect(page.get_by_role('heading',name='Physical point',exact=True)).to_be_visible()
    assert len(context.request.get(project).json()['nodes'])==2
    page.get_by_label('Active sheet',exact=True).select_option('1')
    expect(page.locator('.source-feature')).to_have_count(9)
    page.get_by_role('button',name='Detected features',exact=True).click()
    expect(page.locator('.source-feature-card')).to_have_count(9)
    page.get_by_role('button',name='Toggle detected flange locations',exact=True).click()
    expect(page.locator('.source-feature')).to_have_count(0)
    page.locator('.sidebar').get_by_role('button',name='Excel results',exact=True).click()
    page.get_by_role('tab',name='Source features',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(26)
    with page.expect_download() as download:page.get_by_role('link',name='Export Excel (.xlsx)',exact=True).click()
    book=load_workbook(io.BytesIO(Path(download.value.path()).read_bytes()),read_only=True,data_only=True)
    assert book['Source features'].max_row==31
    assert all(row[5] is None for row in book['Source features'].iter_rows(min_row=6,values_only=True))
    book.close()
    print('PASS: real 13 flange/26 interface proposals, drawing overlay, editable separate face/dot points, retained unknown stations, no duplicate on reselect and shared numeric website/Excel table.',flush=True)
