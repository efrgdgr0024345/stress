"""Real-source exception explanations/reopening never waive missing facts."""
import hashlib
from pathlib import Path
from playwright.sync_api import expect

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'
SHA='7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59'


def exercise_real_source_exceptions(page,context,base):
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SHA
    response=context.request.post(base+'/api/v1/projects',data={
        'title':'1010 real source exception review — DISPOSABLE SOFTWARE VALIDATION',
        'line_id':'8-PG-JE3LN2-1010-FUTURE'})
    assert response.ok,response.text();p=response.json();project=base+'/api/v1/projects/'+p['id']
    response=context.request.post(project+'/sources?version=1',multipart={
        'file':{'name':SOURCE.name,'mimeType':'application/pdf','buffer':SOURCE.read_bytes()}})
    assert response.ok,response.text();p=response.json()
    page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
    page.get_by_role('button',name='Locate source interfaces',exact=True).click()
    expect(page.get_by_role('button',name='Refresh source review',exact=True)).to_be_visible(timeout=30000)
    p=context.request.get(project).json()
    assert len(p['nodes'])==47 and p['graph']['edges']==[]
    baseline={n['id']:{k:n.get(k) for k in ('station_mm','number','route','order','coordinates_mm','instances')} for n in p['nodes']}
    assert all(n['station_mm'] is None and n['number'] is None for n in p['nodes'])
    path=project+'/physical-model/source-exceptions'
    report=context.request.get(path).json()
    exception=next(v for v in report['all'] if v['code']=='DIMENSION_WITNESS_MAPPING_UNCONFIRMED')
    assert exception['active'] and exception['color']=='blue' and exception['engineering_approved'] is False
    assert exception['source_sha256']==SHA and exception['evidence'] and exception['source_context_sha256']
    assert not report['station_constraints'] and not report['reviews']

    def open_exception():
        page.get_by_role('button',name='Review source exceptions',exact=True).click()
        dialog=page.get_by_role('dialog',name='Review source exception',exact=True)
        expect(dialog).to_be_visible()
        dialog.get_by_label('Source exception',exact=True).select_option(exception['id'])
        expect(dialog).to_contain_text(exception['evidence'])
        return dialog

    def verify_active(status,decisions):
        state=context.request.get(path).json()
        entry=next(v for v in state['all'] if v['id']==exception['id'])
        assert entry['status']==status and entry['active'] and entry['color']=='blue'
        assert entry['engineering_approved'] is False and entry['resolution'] is None
        assert entry['id'] in {v['id'] for v in state['active']}
        records=[v for v in state['reviews'] if v['exception_id']==exception['id']]
        assert [r['decision'] for r in records]==decisions
        assert all(r['engineering_approved'] is False for r in records)
        assert records[-1]['is_latest'] and records[-1]['current']
        current=context.request.get(project).json()
        assert {n['id']:{k:n.get(k) for k in ('station_mm','number','route','order','coordinates_mm','instances')} for n in current['nodes']}==baseline
        assert current['graph']['edges']==[] and not current.get('review_approval')
        assert not state['station_constraints']
        return state

    retained='SOFTWARE VALIDATION: the printed dimension alone does not establish its physical witness endpoints or an accepted along-centreline constraint. Retain this blue source exception until an authorised engineer supplies and reviews the actual missing proof.'
    dialog=open_exception()
    expect(dialog.get_by_role('button',name='Save source exception review',exact=True)).to_be_disabled()
    dialog.get_by_label('Source exception decision',exact=True).select_option('RETAIN_UNRESOLVED')
    dialog.get_by_label('Source exception review evidence',exact=True).fill(retained)
    dialog.get_by_label('Confirm source exception decision',exact=True).check()
    dialog.get_by_role('button',name='Save source exception review',exact=True).click()
    expect(dialog).to_have_count(0)
    verify_active('RETAINED_UNRESOLVED',['RETAIN_UNRESOLVED'])

    dialog=open_exception()
    expect(dialog).to_contain_text('Retained unresolved')
    history=dialog.get_by_label('Source exception review history',exact=True)
    expect(history).to_be_visible()
    expect(history.get_by_text(retained,exact=True)).to_be_visible()
    reopened='SOFTWARE VALIDATION: reopen this actual source-witness exception for further engineering inspection. Preserve the earlier explanation, original PDF, unknown stations and every unaccepted connection; this review grants no engineering approval.'
    dialog.get_by_label('Source exception decision',exact=True).select_option('REOPEN')
    dialog.get_by_label('Source exception review evidence',exact=True).fill(reopened)
    dialog.get_by_label('Confirm source exception decision',exact=True).check()
    dialog.get_by_role('button',name='Save source exception review',exact=True).click()
    expect(dialog).to_have_count(0)
    state=verify_active('REOPENED',['RETAIN_UNRESOLVED','REOPEN'])
    assert any(r['evidence']==retained for r in state['reviews'])
    page.reload()
    dialog=open_exception()
    expect(dialog).to_contain_text('Reopened')
    history=dialog.get_by_label('Source exception review history',exact=True)
    expect(history).to_be_visible()
    expect(history.get_by_text(reopened,exact=True)).to_be_visible()
    expect(history.get_by_text(retained,exact=True)).to_be_visible()
    page.screenshot(path='/tmp/caesar-screens/real-1010-source-exception-history.png',full_page=True)
    dialog.get_by_role('button',name='Cancel',exact=True).click()
    source=context.request.get(project+'/sources/'+p['sheets'][0]['source_id'])
    assert source.ok and hashlib.sha256(source.body()).hexdigest()==SHA
    print('PASS: exact real source exception retain/reopen history, persistent active blue missing-fact reason, unchanged physical IDs/anchors/stations/XYZ/topology and no invented constraint or engineering approval.',flush=True)
