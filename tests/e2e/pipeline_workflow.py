"""Unattended native slice and an actual editable XLSX download in Chromium."""
import io
from pathlib import Path
import time
import zipfile

from openpyxl import load_workbook
from playwright.sync_api import expect
from tests.integration.test_pipeline import drawing


def exercise_pipeline(page,context,base,directory):
    page.get_by_role('button',name='All projects',exact=True).click()
    page.get_by_role('button',name='New project',exact=True).click()
    page.get_by_label('Project name',exact=True).fill('Automatic native workflow')
    page.get_by_label('Full line ID',exact=False).fill('AUTO-TEST-001')
    path=Path(directory)/'qualified-native.pdf';path.write_bytes(drawing())
    page.locator('.upload-zone input').set_input_files(path)
    page.get_by_role('button',name='Create project',exact=True).click()
    expect(page.locator('.pipeline-banner')).to_contain_text('Review draft ready',timeout=90000)
    expect(page.locator('.node-glyph')).to_have_count(2) # two of four points on the active sheet
    page.locator('.sidebar').get_by_role('button',name='Project flow',exact=True).click()
    expect(page.get_by_role('heading',name='Project flow.',exact=True)).to_be_visible()
    expect(page.locator('.pipeline-stage.complete')).to_have_count(4)
    with page.expect_download() as info:page.get_by_role('link',name='Export Excel',exact=True).click()
    book=load_workbook(io.BytesIO(Path(info.value.path()).read_bytes()));assert book['Nodes']['A6'].value==10;assert book['Nodes']['O7'].value==50;assert book['Nodes']['E7'].value is None;book.close()
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path='/tmp/caesar-screens/pipeline-flow.png',full_page=True)
    page.locator('.sidebar').get_by_role('button',name='Excel results',exact=True).click()
    expect(page.get_by_role('heading',name='Results workbook.',exact=True)).to_be_visible()
    expect(page.locator('.results-grid tbody tr')).to_have_count(4)
    page.get_by_role('tab',name='CAESAR input',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(3)
    page.locator('.results-grid tbody tr').first.click()
    expect(page.get_by_role('dialog',name='Element 10 → 20',exact=True)).to_be_visible()
    for label,value in [('DX (mm)','1000'),('DY (mm)','0'),('DZ (mm)','-50.8'),('Outside diameter (mm)','219.1'),('Wall thickness (mm)','8.18'),('Corrosion allowance (mm)','3'),('CAESAR material code','106'),('Temperature (°C)','80'),('Pressure (MPa)','1.25')]:page.get_by_label(label,exact=True).fill(value)
    page.get_by_label('Engineering source / evidence',exact=True).fill('Synthetic browser property evidence; not approved engineering input')
    page.get_by_role('button',name='Save element',exact=True).click()
    expect(page.get_by_role('dialog')).to_have_count(0)
    expect(page.locator('.results-grid tbody tr').first).to_contain_text('-50.8')
    with page.expect_download() as info:page.get_by_role('link',name='Export Excel (.xlsx)',exact=True).click()
    book=load_workbook(io.BytesIO(Path(info.value.path()).read_bytes()));assert book['CAESAR input']['E6'].value==1000;assert book['CAESAR input']['G6'].value==-50.8;book.close()
    with page.expect_download() as info:page.get_by_role('link',name='CSV tables (.zip)',exact=True).click()
    with zipfile.ZipFile(info.value.path()) as archive:
        assert 'caesar-input.csv' in archive.namelist()
        assert '-50.8' in archive.read('caesar-input.csv').decode('utf-8-sig')
    expect(page.get_by_role('button',name='CAESAR neutral (.cii)',exact=True)).to_be_disabled()
    page.get_by_role('button',name='CAESAR export settings',exact=True).click()
    expect(page.get_by_role('dialog',name='CAESAR neutral export settings',exact=True)).to_be_visible()
    expect(page.get_by_label('CAESAR piping code ID',exact=False)).to_be_visible()
    page.get_by_role('button',name='Close dialog',exact=True).click()
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path='/tmp/caesar-screens/excel-results.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    expect(page.get_by_role('heading',name='Results workbook.',exact=True)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'), 'Mobile results overflow the viewport'
    assert page.locator('.results-table-scroll').evaluate('(e) => e.scrollWidth > e.clientWidth'), 'Wide results must scroll within their own panel'
    page.screenshot(path='/tmp/caesar-screens/excel-results-mobile.png',full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('.sidebar').get_by_role('button',name='Drawing workspace',exact=True).click()
    print('PASS: unattended two-sheet native workflow, proposal flags, project timeline, responsive Excel-style results, saved element properties, editable numeric XLSX/CSV export and gated native CAESAR settings.')
