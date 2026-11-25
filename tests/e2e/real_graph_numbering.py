"""Real source/printed XYZ; a disposable partial software topology, never golden data.

Only four independently inspected real source locations are assigned a deliberately
software-declared order to qualify graph/numbering controls. This does not assert
that the omitted source points are absent or that these test edges are the full
engineering route. No station, length or page-derived physical XYZ is invented.
"""
from copy import deepcopy
from pathlib import Path
import re
import io
from openpyxl import load_workbook
from playwright.sync_api import expect
from tests.e2e.real_drawing import wait_for_drawing

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'
LINE='8-PG-JE3LN2-1010-FUTURE'
SUPPORT_OBSERVATION='53adb8b6-6462-5aa9-a2cf-435484a305da'
TEE_OBSERVATION='3dd7112e-2ef2-5f55-9297-6d7a26a7a045'
PIT_OBSERVATION='bd5d10ea-e81f-5008-83cb-a9ce758262a7'
REASON=('DISPOSABLE SOFTWARE VALIDATION ONLY: explicit partial ordered subset of independently inspected actual '
        'support, common tee, shared continuation and PIT source locations. This software-declared sequence tests '
        'main/branch numbering; it is not the complete accepted 1010 engineering topology. All stations stay unknown.')


def exercise_real_graph_numbering(page,context,base):
    response=context.request.post(base+'/api/v1/projects',data={
        'title':'1010 partial graph numbering — DISPOSABLE SOFTWARE VALIDATION','line_id':LINE})
    assert response.ok,response.text();p=response.json();project=base+'/api/v1/projects/'+p['id']
    response=context.request.post(project+'/sources?version=1',multipart={
        'file':{'name':SOURCE.name,'mimeType':'application/pdf','buffer':SOURCE.read_bytes()}})
    assert response.ok,response.text();p=response.json()
    response=context.request.post(project+'/physical-model/source-points',data={'version':p['version'],'confirmed':True})
    assert response.ok,response.text();p=response.json()
    assert len(p['nodes'])==47 and p['graph']['edges']==[]
    assert all(n['number'] is None and n['station_mm'] is None and n['route'] is None for n in p['nodes'])
    original_source_bytes=SOURCE.read_bytes()
    original_instances={n['id']:deepcopy(n['instances']) for n in p['nodes']}

    def node_for_observation(observation):
        return next(n for n in p['nodes'] if n.get('source_observation',{}).get('id')==observation)

    support=node_for_observation(SUPPORT_OBSERVATION)
    tee=node_for_observation(TEE_OBSERVATION)
    pit=node_for_observation(PIT_OBSERVATION)
    page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
    page.get_by_role('button',name='Review graph and numbering',exact=True).click()
    dialog=page.get_by_role('dialog',name='Review ordered topology',exact=True)
    expect(dialog.get_by_label('Include point '+support['review_label'],exact=True)).to_be_disabled()
    expect(dialog).to_contain_text('47 unassigned points remain outside this graph')
    expect(dialog.get_by_role('button',name='Preview graph and numbering',exact=True)).to_be_disabled()
    dialog.get_by_role('button',name='Cancel',exact=True).click()

    # Confirm the actual printed sheet register before coordinate/identity review.
    for index,sheet in enumerate(p['sheets']):
        assert sheet['printed_id'] in (f'{index+1}OF2',f'{index+1} OF 2',f'SHEET {index+1} OF 2'),sheet['printed_id']
        response=context.request.patch(project+'/sheets/'+sheet['id'],data={
            'version':p['version'],'printed_id':sheet['printed_id'],'line_id':LINE,
            'axis':sheet.get('axis'),'table':sheet.get('table'),'confirm_identity':True})
        assert response.ok,response.text();p=response.json()
    candidates=p['automation']['continuation_candidates']
    left=next(c for c in candidates if c['source_label']=='S1-CONT-SHEET2')
    right=next(c for c in candidates if c['source_label']=='S2-CONT-SHEET1')

    def inspect(point_id,sheet_id):
        nonlocal p
        node=next(n for n in p['nodes'] if n['id']==point_id)
        response=context.request.patch(project+'/nodes/'+point_id,data={
            'version':p['version'],'line_id':node['line_id'],'kind':node['kind'],
            'topology_state':'UNASSIGNED','route':None,'order':None,'dimension':'',
            'instances':node['instances'],'source_location_confirmed':True,
            'source_location_sheet_id':sheet_id,
            'evidence':'DISPOSABLE SOFTWARE VALIDATION: independently inspect the exact current real source feature and anchor. No station, route or engineering approval.'})
        assert response.ok,response.text();p=response.json()

    for candidate in (left,right):
        inspect(candidate['point_id'],candidate['sheet_id'])
        response=context.request.post(project+'/physical-model/source-coordinates/'+candidate['id']+'/accept',data={
            'version':p['version'],'tolerance_text':'0 mm','confirmed':True,
            'evidence':'DISPOSABLE SOFTWARE VALIDATION: actual printed E135ft4-1/4in, S312ft10-3/8in, EL37ft10-3/4in on this independently inspected source. No station accepted.'})
        assert response.ok,response.text();p=response.json()
    # These are identical actual printed process-interface coordinates, not a
    # flange face or a nearby pixel-derived point. Accept this one exact identity.
    response=context.request.post(project+'/continuations',data={
        'version':p['version'],'left_point_id':left['point_id'],'right_point_id':right['point_id'],
        'left_candidate_id':left['id'],'right_candidate_id':right['id'],
        'left_size':'8 in','right_size':'8 in','tolerance_text':'0 mm',
        'decision':'ACCEPT_IDENTITY','topology_confirmed':True,'confirmed':True,
        'evidence':'DISPOSABLE SOFTWARE VALIDATION: reciprocal actual sheet1/sheet2 process-interface labels, independently inspected identical signed printed XYZ and 8in source size. No station or full route approval.'})
    assert response.ok,response.text();p=response.json()
    shared=next(n for n in p['nodes'] if n['id']==left['point_id'])
    assert p['point_aliases'][right['point_id']]==shared['id'] and len(shared['instances'])==2
    assert len(p['nodes'])==46 and all(n['station_mm'] is None and n['number'] is None for n in p['nodes'])
    assert p['graph']['edges']==[]
    for node in (support,tee,pit):inspect(node['id'],node['instances'][0]['sheet_id'])
    before=deepcopy(p)
    labels={n['id']:n['review_label'] for n in p['nodes']}
    selected=[(support,'main',0,None),(tee,'main',1,None),(shared,'main',2,None),(pit,'branch-01',0,tee['id'])]

    page.reload()
    page.get_by_role('button',name='Review graph and numbering',exact=True).click()
    dialog=page.get_by_role('dialog',name='Review ordered topology',exact=True)
    for node,route,order,takeoff in selected:
        name=labels[node['id']]
        dialog.get_by_label('Include point '+name,exact=True).check()
        dialog.get_by_label('Topology state '+name,exact=True).select_option('ASSIGNED')
        expect(dialog.get_by_label('Route '+name,exact=True)).to_have_value('')
        expect(dialog.get_by_label('Order '+name,exact=True)).to_have_value('')
        dialog.get_by_label('Route '+name,exact=True).fill(route)
        dialog.get_by_label('Order '+name,exact=True).fill(str(order))
        if takeoff:dialog.get_by_label('Takeoff '+name,exact=True).select_option(takeoff)
        dialog.get_by_label('Confirm declared topology '+name,exact=True).check()
    dialog.get_by_label('Route review reason',exact=True).fill(REASON)
    dialog.get_by_label('Confirm topology review scope',exact=True).check()
    with page.expect_response(lambda r:'/topology-review/preview' in r.url and r.request.method=='POST') as response:
        dialog.get_by_role('button',name='Preview graph and numbering',exact=True).click()
    assert response.value.ok,response.value.text();preview=response.value.json()
    assert preview['can_apply'] and preview['summary']['assigned']==4 and preview['summary']['unassigned']==42
    assert preview['summary']['edges']==3 and preview['summary']['connected_assigned'] and not preview['summary']['complete']
    assert {'GRAPH_XYZ_UNPROVED','GRAPH_STATION_UNPROVED','TOPOLOGY_UNASSIGNED'}<={i['code'] for i in preview['issues']}
    mapping={m['point_id']:m['new'] for m in preview['numbering_map']}
    assert [mapping[n['id']] for n,_,_,_ in selected]==[10,20,30,100]
    assert all(n['number'] is None and n['station_mm'] is None for n in context.request.get(project).json()['nodes'])
    expect(dialog.get_by_role('img',name='Reviewed route schematic',exact=True)).to_be_visible()
    expect(dialog).to_contain_text('Spacing is not physical length or source geometry')
    expect(dialog.get_by_role('table',name='Preview numbering map',exact=True)).to_contain_text('100')
    dialog.get_by_role('img',name='Reviewed route schematic',exact=True).scroll_into_view_if_needed()
    page.screenshot(path='/tmp/caesar-screens/real-1010-graph-preview.png',full_page=True)
    dialog.get_by_role('img',name='Reviewed route schematic',exact=True).screenshot(path='/tmp/caesar-screens/real-1010-graph-schematic.png')

    # Editing after preview invalidates the hash-bound apply control. Duplicate
    # declared order is a blocking issue instead of a UUID-selected adjacency.
    dialog.get_by_label('Order '+labels[tee['id']],exact=True).fill('0')
    expect(dialog.get_by_role('button',name='Apply previewed graph and numbering',exact=True)).to_have_count(0)
    dialog.get_by_label('Confirm declared topology '+labels[tee['id']],exact=True).check()
    dialog.get_by_label('Confirm topology review scope',exact=True).check()
    with page.expect_response(lambda r:'/topology-review/preview' in r.url and r.request.method=='POST') as response:
        dialog.get_by_role('button',name='Preview graph and numbering',exact=True).click()
    assert response.value.ok,response.value.text();invalid=response.value.json()
    assert not invalid['can_apply'] and 'DUPLICATE_ROUTE_ORDER' in {i['code'] for i in invalid['issues']}
    expect(dialog.get_by_role('button',name='Apply previewed graph and numbering',exact=True)).to_be_disabled()
    dialog.get_by_label('Order '+labels[tee['id']],exact=True).fill('1')
    dialog.get_by_label('Confirm declared topology '+labels[tee['id']],exact=True).check()
    dialog.get_by_label('Confirm topology review scope',exact=True).check()
    with page.expect_response(lambda r:'/topology-review/preview' in r.url and r.request.method=='POST') as response:
        dialog.get_by_role('button',name='Preview graph and numbering',exact=True).click()
    assert response.value.ok,response.value.text()
    with page.expect_response(lambda r:'/topology-review/apply' in r.url and r.request.method=='POST') as response:
        dialog.get_by_role('button',name='Apply previewed graph and numbering',exact=True).click()
    assert response.value.ok,response.value.text();expect(dialog).not_to_be_visible()
    p=context.request.get(project).json()
    by_id={n['id']:n for n in p['nodes']}
    assert [by_id[n['id']]['number'] for n,_,_,_ in selected]==[10,20,30,100]
    assert len(p['nodes'])==46 and len(p['graph']['edges'])==3
    assert all(n['station_mm'] is None for n in p['nodes'])
    assert all(n['number'] is None and n['route'] is None for n in p['nodes'] if n['id'] not in {r[0]['id'] for r in selected})
    assert all(n['instances']==next(b['instances'] for b in before['nodes'] if b['id']==n['id']) for n in p['nodes'])
    assert p['point_aliases']==before['point_aliases']
    assert p['physical_model']['constraints']==before['physical_model']['constraints']

    # A pure repeated numbering review must preserve all engineering values,
    # provenance, reason lists, current numbering map, identities and history.
    stable=deepcopy(p)
    page.get_by_role('button',name='Review graph and numbering',exact=True).click()
    dialog=page.get_by_role('dialog',name='Review ordered topology',exact=True)
    expect(dialog.get_by_role('table',name='Topology assignment review',exact=True)).to_contain_text('2 source depictions')
    dialog.get_by_label('Numbering review history',exact=True).locator('summary').click()
    expect(dialog.get_by_label('Numbering review history',exact=True)).to_contain_text('Retired source identity')
    expect(dialog.get_by_label('Numbering review history',exact=True)).to_contain_text(right['point_id'])
    dialog.get_by_label('Route review reason',exact=True).fill('DISPOSABLE SOFTWARE VALIDATION ONLY: repeat numbering of the existing explicit partial graph, with no geometry, source proof, evidence, identity or route changes.')
    dialog.get_by_label('Confirm topology review scope',exact=True).check()
    with page.expect_response(lambda r:'/topology-review/preview' in r.url and r.request.method=='POST') as response:
        dialog.get_by_role('button',name='Preview graph and numbering',exact=True).click()
    assert response.value.ok,response.value.text()
    assert response.value.json()['changes']==[] and response.value.json()['can_apply']
    with page.expect_response(lambda r:'/topology-review/apply' in r.url and r.request.method=='POST') as response:
        dialog.get_by_role('button',name='Apply previewed graph and numbering',exact=True).click()
    assert response.value.ok,response.value.text();expect(dialog).not_to_be_visible()
    p=context.request.get(project).json()
    for key in ('nodes','numbering_map','numbering_history','point_aliases','physical_model'):
        assert p[key]==stable[key],key
    assert SOURCE.read_bytes()==original_source_bytes
    assert all(n['instances']==original_instances[n['id']] for n in p['nodes'] if n['id']!=shared['id'])

    # Web and exported workbook use the same physical UUID graph and full map.
    page.get_by_role('tab',name='Graph edges',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(3)
    page.get_by_role('tab',name='Numbering map',exact=True).click()
    expect(page.locator('.results-grid tbody tr')).to_have_count(47)
    expect(page.locator('.results-grid tbody')).to_contain_text('RETIRED_ALIAS')
    with page.expect_download() as downloaded:
        page.get_by_role('link',name='Export Excel (.xlsx)',exact=True).click()
    book=load_workbook(io.BytesIO(Path(downloaded.value.path()).read_bytes()),read_only=True,data_only=True)
    def rows(name):
        sheet=book[name]
        headers=[cell.value for cell in sheet[5]]
        return [dict(zip(headers,values)) for values in sheet.iter_rows(min_row=6,values_only=True)]
    nodes=rows('Nodes')
    assert len(nodes)==46 and sorted(r['Node'] for r in nodes if r['Node'] is not None)==[10,20,30,100]
    assert all(r['Accepted station (mm)'] is None for r in nodes)
    assert {r['Physical point ID'] for r in nodes}=={n['id'] for n in p['nodes']}
    edges=rows('Graph edges')
    assert len(edges)==3
    assert {(r['From physical point ID'],r['To physical point ID']) for r in edges}=={(e['from'],e['to']) for e in p['graph']['edges']}
    assert all(r['Comparable route span (mm)'] is None for r in edges)
    assert all(r[key] is None for r in edges for key in ('Source-constrained DX (mm)','Source-constrained DY (mm)','Source-constrained DZ (mm)'))
    mapping_rows=rows('Numbering map')
    assert len(mapping_rows)==47
    current=[r for r in mapping_rows if r['Physical identity state']!='RETIRED_ALIAS']
    assert len(current)==46 and sum(r['Current CAESAR number'] is None for r in current)==42
    assert sorted(r['Current CAESAR number'] for r in current if r['Current CAESAR number'] is not None)==[10,20,30,100]
    alias=next(r for r in mapping_rows if r['Physical identity state']=='RETIRED_ALIAS')
    assert alias['Original physical point ID']==right['point_id'] and alias['Current physical point ID']==shared['id']
    assert alias['Current CAESAR number']==30 and alias['Previous CAESAR number'] is None
    history=rows('Numbering history')
    assert history[-1]['Project revision']==stable['numbering_history'][-1]['revision']
    assert history[-1]['Current physical points']==46 and history[-1]['Retained identity aliases']==1
    assert history[-1]['Complete numbering event SHA256']==stable['numbering_history'][-1]['sha256']
    book.close()

    # The one physical number has depictions on both original sheets.
    page.locator('.sidebar').get_by_role('button',name='Drawing workspace',exact=True).click()
    wait_for_drawing(page,'.paper canvas')
    expect(page.locator('.node-glyph text').filter(has_text=re.compile('^30$'))).to_have_count(1)
    page.get_by_label('Next sheet',exact=True).click();wait_for_drawing(page,'.paper canvas')
    expect(page.locator('.node-glyph text').filter(has_text=re.compile('^30$'))).to_have_count(1)
    page.screenshot(path='/tmp/caesar-screens/real-1010-graph-numbering.png',full_page=True)
    print('PASS: exact-source independent inspections/printed XYZ and shared identity; explicit software partial graph preview/apply; main10/20/30, tee branch100; duplicate-order gate; unchanged numbering-only rerun; two-sheet number and numeric current+alias workbook/history;42 unassigned and all stations unknown.',flush=True)
