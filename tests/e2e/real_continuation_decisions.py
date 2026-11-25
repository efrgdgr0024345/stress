"""Source-only decisions on the exact real PDF; no accepted model geometry."""
from pathlib import Path
from playwright.sync_api import expect

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'


def exercise_real_continuation_decisions(page,context,base):
    response=context.request.post(base+'/api/v1/projects',data={
        'title':'1010 real continuation source decisions — software validation',
        'line_id':'8-PG-JE3LN2-1010-FUTURE'})
    assert response.ok,response.text();p=response.json()
    project=base+'/api/v1/projects/'+p['id']
    response=context.request.post(project+'/sources?version=1',multipart={
        'file':{'name':SOURCE.name,'mimeType':'application/pdf','buffer':SOURCE.read_bytes()}})
    assert response.ok,response.text();p=response.json()
    page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
    page.get_by_role('button',name='Locate source interfaces',exact=True).click()
    expect(page.get_by_role('button',name='Refresh source review',exact=True)).to_be_visible(timeout=30000)
    p=context.request.get(project).json()
    initial_ids={n['id'] for n in p['nodes']}
    assert all(n['station_mm'] is None and n['number'] is None and n['route'] is None for n in p['nodes'])
    assert p['graph']['edges']==[]
    report=context.request.get(project+'/continuations').json()
    assert len(report['candidates'])==4
    candidate=next(c for c in report['candidates'] if '1093' in c['source_text'])
    point=next(n for n in p['nodes'] if n['id']==candidate['point_id'])
    assert point['review_label'].startswith('P') and point['number'] is None

    def open_from_row():
        page.get_by_role('tab',name='Continuation sources',exact=True).click()
        page.locator('.results-grid tbody tr').filter(has_text='1093').click()
        dialog=page.get_by_role('dialog',name='Review source reference',exact=True)
        expect(dialog).to_be_visible()
        expect(dialog).to_contain_text(candidate['source_text'])
        expect(dialog).to_contain_text(point['review_label'])
        return dialog

    def fill(dialog,decision,reason,evidence):
        dialog.get_by_label('Source reference decision',exact=True).select_option(decision)
        dialog.get_by_label('Source decision reason',exact=True).select_option(reason)
        dialog.get_by_label('Source reference evidence',exact=True).fill(evidence)
        dialog.get_by_label('Confirm source reference decision and evidence',exact=True).check()

    def unchanged_geometry(expected_status):
        current=context.request.get(project).json()
        assert {n['id'] for n in current['nodes']}==initial_ids
        assert all(n['station_mm'] is None and n['number'] is None and n['topology_state']=='UNASSIGNED' for n in current['nodes'])
        assert current['graph']['edges']==[]
        state=context.request.get(project+'/continuations').json()
        review=next(r for r in state['source_reviews'] if r['candidate_id']==candidate['id'] and r['is_latest'])
        assert review['current'] and review['effective_status']==expected_status
        assert review['engineering_approved'] is False
        return current,state

    dialog=open_from_row()
    fill(dialog,'DECLARE_EXTERNAL_BOUNDARY','MISSING_PEER_IN_PACK',
        'SOFTWARE VALIDATION: the printed 1093 peer is outside this uploaded 1010 pack; record the source boundary without accepting coordinates, identity or topology.')
    dialog.get_by_role('button',name='Save source reference decision',exact=True).click()
    expect(dialog).to_have_count(0)
    p,report=unchanged_geometry('EXTERNAL_BOUNDARY')

    # The accessible button permits inspecting any source and its decision history.
    page.get_by_role('button',name='Review source reference',exact=True).click()
    dialog=page.get_by_role('dialog',name='Review source reference',exact=True)
    dialog.get_by_label('Source continuation reference',exact=True).select_option(candidate['id'])
    expect(dialog).to_contain_text('External boundary')
    expect(dialog).to_contain_text('Recorded source evidence:')
    fill(dialog,'REOPEN','SOURCE_INTERFACE_UNCONFIRMED',
        'SOFTWARE VALIDATION: reopen the source reference for further interface review; retain the earlier external-boundary decision and all unproved engineering values.')
    dialog.get_by_role('button',name='Save source reference decision',exact=True).click()
    expect(dialog).to_have_count(0)
    p,report=unchanged_geometry('REOPENED')
    review_count=len(report['source_reviews'])

    # Captured modal revisions must reject concurrent edits, even if the edit
    # merely resaves the same source register and invents no engineering fact.
    dialog=open_from_row()
    fill(dialog,'REJECT_MATCH','MISSING_PEER_IN_PACK',
        'SOFTWARE VALIDATION: reject an unsupported in-pack match because the referenced 1093 peer is absent; no connection or source coordinate is accepted.')
    sheet=p['sheets'][0]
    changed=context.request.patch(project+'/sheets/'+sheet['id'],data={
        'version':p['version'],'printed_id':sheet.get('printed_id',''),'line_id':sheet['line_id'],
        'axis':sheet.get('axis'),'table':sheet.get('table'),'confirm_identity':False})
    assert changed.ok,changed.text()
    dialog.get_by_role('button',name='Save source reference decision',exact=True).click()
    expect(dialog.get_by_role('alert')).to_contain_text('changed')
    assert len(context.request.get(project+'/continuations').json()['source_reviews'])==review_count
    dialog.get_by_role('button',name='Cancel',exact=True).click()
    page.reload()
    dialog=open_from_row()
    fill(dialog,'REJECT_MATCH','MISSING_PEER_IN_PACK',
        'SOFTWARE VALIDATION: after refreshing the revision, reject the unsupported in-pack match to the missing 1093 peer; the endpoint and unknown engineering data remain preserved.')
    dialog.get_by_role('button',name='Save source reference decision',exact=True).click()
    expect(dialog).to_have_count(0)
    p,report=unchanged_geometry('REJECTED_MATCH')
    decisions={r['decision'] for r in report['source_reviews'] if r['candidate_id']==candidate['id']}
    assert {'DECLARE_EXTERNAL_BOUNDARY','REOPEN','REJECT_MATCH'}<=decisions
    assert all(r['engineering_approved'] is False for r in report['source_reviews'])
    expect(page.locator('.results-grid tbody')).to_contain_text('REJECTED')
    page.screenshot(path='/tmp/caesar-screens/real-1010-continuation-decisions.png',full_page=True)
    print('PASS: real source reference row/button, P-label and evidence, external boundary, reversible reopen/reject history, stale-revision rejection, and unchanged unknown stations/topology/physical IDs.',flush=True)
