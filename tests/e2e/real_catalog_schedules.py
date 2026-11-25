"""Actual1010 catalog/schedule controls with honest missing-data dispositions.

The exact user-provided627-row reference workbook is required. Its published
source values qualify the adapter/provenance; they never prove the actual
project manufacturer or fill missing facing/type/valve data by substitution.
"""
from pathlib import Path
import hashlib
import io
import os
from openpyxl import load_workbook
from playwright.sync_api import expect

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'
CATALOG_SHA='84cc71a66c2f47a3e70f27adf7c286cd346fdf722d5dfcf50158085d2e2d356a'
CATALOG=Path(__file__).resolve().parents[2]/'fixtures/catalogs/PIPE100_Flange_Weights_B16_5_B16_47_API6A_Numbers.xlsx'
LINE='8-PG-JE3LN2-1010-FUTURE'


def exercise_real_catalog_schedules(page,context,base):
    catalog_path=Path(os.environ.get('CAESAR_REAL_CATALOG_XLSX',str(CATALOG)))
    assert catalog_path.is_file(),'The exact627-row user reference workbook is required for real catalog qualification.'
    raw=catalog_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==CATALOG_SHA
    response=context.request.post(base+'/api/v1/catalogs/import',multipart={
        'file':{'name':catalog_path.name,'mimeType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','buffer':raw}})
    assert response.ok,response.text();catalog=response.json()
    versions=context.request.get(base+'/api/v1/catalogs/'+catalog['id']+'/versions').json()
    assert len(versions)==4
    assert sorted(len(v['data']['records']) for v in versions)==[39,108,132,348]
    assert all(v['data']['status']=='PENDING_APPROVAL' and v['data']['approval'] is None for v in versions)
    assert all(r['facing']=='UNSPECIFIED' and r['source_sha256']==CATALOG_SHA for v in versions for r in v['data']['records'])
    assert all(r['quality']!='MANUFACTURER_CONFIRMED' for v in versions for r in v['data']['records'])
    assert not any(v['data']['source_sha256']==CATALOG_SHA for v in context.request.get(base+'/api/v1/approved-catalogs').json())
    response=context.request.post(base+'/api/v1/projects',data={
        'title':'1010 real catalog schedules — DISPOSABLE SOFTWARE VALIDATION','line_id':LINE})
    assert response.ok,response.text();p=response.json();project=base+'/api/v1/projects/'+p['id']
    response=context.request.post(project+'/sources?version=1',multipart={
        'file':{'name':SOURCE.name,'mimeType':'application/pdf','buffer':SOURCE.read_bytes()}})
    assert response.ok,response.text();p=response.json()
    response=context.request.post(project+'/physical-model/source-points',data={'version':p['version'],'confirmed':True})
    assert response.ok,response.text();p=response.json()
    original_nodes=p['nodes'];original_graph=p['graph'];original_sha=[s['sha256'] for s in p['sheets']]
    report=context.request.get(project+'/catalog-review').json()
    assert len(report['rows'])==6
    assert sorted((r['family'],r['quantity']) for r in report['rows'])==[('flange',3),('flange',4),('flange',6),('valve',1),('valve',1),('valve',3)]
    assert sum(r['occurrence_count'] for r in report['rows'])==18
    assert len(report['classification_rows'])==1 and report['classification_rows'][0]['family']=='other'
    assert all(v is None for v in report['classification_rows'][0]['values'].values())
    assert all(r['project_manufacturer']['status']=='UNCONFIRMED' for r in report['rows'])
    assert all(all(v is None for v in r['values'].values()) for r in report['rows'])
    manifest=[v for v in report['catalog_manifest'] if v['source_sha256']==CATALOG_SHA]
    assert len(manifest)==4 and sum(v['record_count'] for v in manifest)==627
    assert all(v['status']=='PENDING_APPROVAL' for v in manifest)

    page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
    page.get_by_role('button',name='Review catalogs and schedules',exact=True).click()
    dialog=page.get_by_role('dialog',name='Project catalogs and schedules',exact=True)
    expect(dialog).to_contain_text('Catalog source quality does not confirm the installed manufacturer')
    expect(dialog.get_by_label('Components requiring classification',exact=True)).to_contain_text('not counted as a valve')
    for sheet,count in zip(p['sheets'],(2,4)):
        table=dialog.get_by_role('table',name='Schedule table '+sheet['printed_id'],exact=True)
        expect(table.locator('tbody tr')).to_have_count(count)
        expect(table).to_contain_text('N/A')
    dialog.get_by_label('Registered catalog sources',exact=True).locator('summary').first.click()
    expect(dialog.get_by_role('table',name='Registered catalog dataset inventory',exact=True)).to_contain_text('348')
    expect(dialog.get_by_role('table',name='Registered catalog dataset inventory',exact=True)).to_contain_text('39')
    with page.expect_response(lambda r:'/catalog-review/prepare' in r.url and r.request.method=='POST') as prepared:
        dialog.get_by_role('button',name='Prepare catalog proposals',exact=True).click()
    assert prepared.value.ok,prepared.value.text()
    expect(dialog.get_by_role('button',name='Refresh catalog proposals',exact=True)).to_be_enabled()
    report=context.request.get(project+'/catalog-review').json()
    assert report['prepared'] and all(not r['exact_candidates'] for r in report['rows'])
    expect(dialog.get_by_label('Catalog disposition',exact=True).locator('option[value="ACCEPT_EXACT_MATCH"]')).to_have_attribute('disabled','')

    def choose(row):
        dialog.get_by_label('Source component for review',exact=True).select_option(row['material_id'])
        expect(dialog).to_contain_text(row['description'])

    def save_na(row):
        choose(row)
        dialog.get_by_label('Catalog disposition',exact=True).select_option('DECLARE_NA')
        reason='CATALOG_FACING_UNSPECIFIED' if row['family']=='flange' else 'VALVE_MANUFACTURER_DATA_UNAVAILABLE'
        dialog.get_by_label('Catalog decision reason',exact=True).select_option(reason)
        evidence=('DISPOSABLE SOFTWARE VALIDATION: actual source flange requires API6A RTJ and distinct API bore/type proof. '
                  'The registered reference workbook does not specify facing; no project exact match or zero weight may be invented.' if row['family']=='flange' else
                  'DISPOSABLE SOFTWARE VALIDATION: actual source valve weight and face-to-face length are not supplied by the available flange reference data. Obtain manufacturer-specific valve data; retain N/A, never zero.')
        dialog.get_by_label('Catalog source evidence',exact=True).fill(evidence)
        dialog.get_by_label('Confirm catalog source decision',exact=True).check()
        with page.expect_response(lambda r:'/catalog-review/decision' in r.url and r.request.method=='POST') as saved:
            dialog.get_by_role('button',name='Save catalog decision',exact=True).click()
        assert saved.value.ok,saved.value.text()
        expect(dialog.get_by_role('button',name='Save catalog decision',exact=True)).to_be_disabled()

    for row in report['rows']:save_na(row)
    report=context.request.get(project+'/catalog-review').json()
    assert all(r['latest_review']['decision']=='DECLARE_NA' and r['latest_review']['current'] for r in report['rows'])
    assert all(not s['numeric_complete'] for s in report['sheets'])
    assert all(all(v is None for v in r['values'].values()) for r in report['rows'])
    assert all(r['project_manufacturer']['status']=='UNCONFIRMED' for r in report['rows'])
    assert all(r['engineering_approved'] is False for r in report['rows'])

    # N/A is a reversible source-bound disposition, not a numeric/model approval.
    row=report['rows'][0];choose(row)
    dialog.get_by_label('Catalog decision history',exact=True).locator('summary').first.click()
    expect(dialog.get_by_label('Catalog decision history',exact=True)).to_contain_text('Declare N/A',ignore_case=True)
    dialog.get_by_label('Catalog disposition',exact=True).select_option('REOPEN')
    dialog.get_by_label('Catalog source evidence',exact=True).fill('DISPOSABLE SOFTWARE VALIDATION: reopen this missing-data disposition for additional independent source/catalog review; preserve unknown weights and earlier source evidence.')
    dialog.get_by_label('Confirm catalog source decision',exact=True).check()
    with page.expect_response(lambda r:'/catalog-review/decision' in r.url and r.request.method=='POST') as reopened:
        dialog.get_by_role('button',name='Save catalog decision',exact=True).click()
    assert reopened.value.ok,reopened.value.text()
    report=context.request.get(project+'/catalog-review').json()
    assert next(r for r in report['rows'] if r['material_id']==row['material_id'])['latest_review']['decision']=='REOPEN'
    save_na(row)

    # Maker evidence remains an independent, explicitly reviewed decision.
    choose(row)
    dialog.get_by_label('Review evidence type',exact=True).select_option('manufacturer')
    expect(dialog.get_by_label('Manufacturer evidence decision',exact=True)).to_have_value('REOPEN')
    expect(dialog).to_contain_text('Current project manufacturer: Unconfirmed')
    expect(dialog.get_by_label('Manufacturer evidence history',exact=True)).to_contain_text('No independent manufacturer confirmation recorded')
    dialog.get_by_label('Independent manufacturer source evidence',exact=True).fill('DISPOSABLE SOFTWARE VALIDATION: actual installed manufacturer/model is not proved by this reference catalog. Reopen independent maker review; do not confirm unknown supplier details.')
    dialog.get_by_label('Confirm independent manufacturer evidence',exact=True).check()
    with page.expect_response(lambda r:'/catalog-review/manufacturer' in r.url and r.request.method=='POST') as maker:
        dialog.get_by_role('button',name='Save manufacturer evidence',exact=True).click()
    assert maker.value.ok,maker.value.text()
    report=context.request.get(project+'/catalog-review').json()
    assert all(r['project_manufacturer']['status']=='UNCONFIRMED' for r in report['rows'])
    assert all(r['decision']!='CONFIRM' for r in report['manufacturer_reviews'])

    # Captured optimistic revision must reject a concurrent write.
    choose(row)
    dialog.get_by_label('Catalog source evidence',exact=True).fill('DISPOSABLE SOFTWARE VALIDATION: this outdated modal must not apply a decision after a concurrent unchanged source register save.')
    dialog.get_by_label('Confirm catalog source decision',exact=True).check()
    p=context.request.get(project).json();sheet=p['sheets'][0]
    response=context.request.patch(project+'/sheets/'+sheet['id'],data={
        'version':p['version'],'printed_id':sheet['printed_id'],'line_id':sheet['line_id'],
        'axis':sheet.get('axis'),'table':sheet.get('table'),'confirm_identity':False})
    assert response.ok,response.text()
    review_count=len(report['reviews'])
    dialog.get_by_role('button',name='Save catalog decision',exact=True).click()
    expect(dialog.get_by_role('alert')).to_contain_text('changed',ignore_case=True)
    assert len(context.request.get(project+'/catalog-review').json()['reviews'])==review_count
    dialog.get_by_role('button',name='Close',exact=True).click()
    page.reload()
    p=context.request.get(project).json()
    assert p['nodes']==original_nodes and p['graph']==original_graph
    assert [s['sha256'] for s in p['sheets']]==original_sha
    assert all(n['station_mm'] is None and n['number'] is None for n in p['nodes'])
    assert all(not m.get('catalog_match') for m in p['materials'])
    # The source file and registered workbook are retained byte-identically.
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==original_sha[0]
    assert hashlib.sha256(catalog_path.read_bytes()).hexdigest()==CATALOG_SHA
    # The website, numeric workbook and retained decisions share these facts.
    page.get_by_role('tab',name='Catalog schedules',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(6)
    expect(page.locator('.results-grid tbody')).to_contain_text('DECLARED_NA')
    page.get_by_role('tab',name='Catalog occurrences',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(18)
    with page.expect_download() as downloaded:
        page.get_by_role('link',name='Export Excel (.xlsx)',exact=True).click()
    book=load_workbook(io.BytesIO(Path(downloaded.value.path()).read_bytes()),read_only=True,data_only=True)
    def workbook_rows(name):
        sheet=book[name];headers=[cell.value for cell in sheet[5]]
        return [dict(zip(headers,values)) for values in sheet.iter_rows(min_row=6,values_only=True)]
    schedules=workbook_rows('Catalog schedules')
    assert len(schedules)==6
    assert [sum(r['PDF page']==page_no for r in schedules) for page_no in (1,2)]==[2,4]
    assert sorted(r['Source count'] for r in schedules)==[1,1,3,3,4,6]
    assert all(isinstance(r['Source count'],int) and isinstance(r['Physical occurrences'],int) for r in schedules)
    assert sum(r['Physical occurrences'] for r in schedules)==18
    assert all(r['Project catalog state']=='DECLARED_NA' and r['Latest review decision']=='DECLARE_NA' for r in schedules)
    assert all(r['Project manufacturer state']=='UNCONFIRMED' and r['Confirmed project manufacturer'] is None and r['Confirmed project model'] is None for r in schedules)
    for row in schedules:
        assert all(row[key] is None for key in ('W_flange / valve weight (N)','Flange + half bolting total (N)','Flange + full bolting total (N)','Assembly weight includes bolting (N)','Valve length (mm)'))
        assert row['Source PDF SHA256']==original_sha[0] and len(row['Reviewed source context SHA256'])==64
        assert row['Missing-data reasons'] and row['Review evidence'] and row['Visual source transcription (proposal)']
        assert row['Source row box (PDF points only)'] not in (None,'None')
    occurrences=workbook_rows('Catalog occurrences')
    assert len(occurrences)==18 and len({r['Physical occurrence ID'] for r in occurrences})==18
    assert [sum(r['PDF page']==page_no for r in occurrences) for page_no in (1,2)]==[5,13]
    assert all(r['Catalog state']=='DECLARED_NA' for r in occurrences)
    assert all(r[key] is None for r in occurrences for key in ('W_flange / valve weight (N)','Flange + half bolting total (N)','Flange + full bolting total (N)','Valve length (mm)'))
    decisions=workbook_rows('Catalog decisions')
    assert len(decisions)==8 and {r['Review decision'] for r in decisions}=={'DECLARE_NA','REOPEN'}
    assert sum(r['Review state']=='CURRENT' for r in decisions)==6
    assert all(r['Source review evidence'] and len(r['Source context SHA256'])==64 and len(r['Catalog manifest SHA256'])==64 for r in decisions)
    makers=workbook_rows('Manufacturer reviews')
    assert len(makers)==1 and makers[0]['Project decision']=='REOPEN'
    assert makers[0]['Declared manufacturer'] is None and makers[0]['Declared model'] is None
    assert all(row['Accepted station (mm)'] is None for row in workbook_rows('Nodes'))
    book.close()
    page.get_by_role('button',name='Review catalogs and schedules',exact=True).click()
    dialog=page.get_by_role('dialog',name='Project catalogs and schedules',exact=True)
    page.screenshot(path='/tmp/caesar-screens/real-1010-catalog-schedules.png',full_page=True)
    dialog.get_by_role('button',name='Close',exact=True).click()
    print('PASS: real1010 six inventory rows/eighteen occurrences, both sheet schedules with explicit N/A, source-bound reversible catalog history, independent unconfirmed maker evidence, stale-modal rejection, numeric/evidence-linked XLSX6schedules18occurrences8decisions, unchanged unknown geometry.'+' Actual canonical627rows/hash/provenance/pending approval qualified.',flush=True)
