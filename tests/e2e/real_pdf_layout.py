"""Actual47-point native PDF layout and every-object edit/save/reopen proof.

All graphic acceptance here is labelled disposable software validation. No
station, physical route/XYZ, catalog number or engineering approval is invented.
The round trip uses a PDF library, not an Adobe/Foxit application qualification.
"""
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin
import io
import json
import zipfile
import fitz
from playwright.sync_api import expect
from packages.pdf import content_hash
from tests.e2e.real_drawing import wait_for_drawing

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'
LINE='8-PG-JE3LN2-1010-FUTURE'
POINT_ROLES={'leader','bubble','number','point-warning'}
AXIS_ROLES={f'axis-{axis}-{kind}' for axis in 'XYZ' for kind in ('line','label')}
MOMENT_ROLES={f'moment-{axis}-{kind}' for axis in 'XYZ' for kind in ('line','label')}


def _manifest_rows(value):
    return value.get('annotations',value.get('manifest',[])) if isinstance(value,dict) else value


def _segment_crosses_rect(first,second,rectangle):
    """Independent graphic-only collision assertion, using segment orientation."""
    rect=fitz.Rect(rectangle)
    if rect.contains(fitz.Point(first)) or rect.contains(fitz.Point(second)):return True
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def intersects(a,b,c,d):
        # Inclusive intersection; collinear segments also require overlapping bounds.
        values=(cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b))
        return (values[0]*values[1]<=0 and values[2]*values[3]<=0 and
            max(min(a[0],b[0]),min(c[0],d[0]))<=min(max(a[0],b[0]),max(c[0],d[0])) and
            max(min(a[1],b[1]),min(c[1],d[1]))<=min(max(a[1],b[1]),max(c[1],d[1])))
    corners=[list(rect.tl),list(rect.tr),list(rect.br),list(rect.bl),list(rect.tl)]
    return any(intersects(first,second,a,b) for a,b in zip(corners,corners[1:]))


def _check_source_clearance(pdf,manifest,report):
    by_name={row['name']:row for row in manifest}
    by_sheet={sheet['sheet_id']:sheet for sheet in report['sheets']}
    originals={}
    with fitz.open(SOURCE) as source:
        for page in source:
            originals[page.number]={annotation.info.get('id'):{'type':annotation.type[1],
                'subject':annotation.info.get('subject'),'blend':source.xref_get_key(annotation.xref,'BM')}
                for annotation in page.annots() or []}
    def on_segment(point,segment):
        a,b=segment;length=max(.001,((b[0]-a[0])**2+(b[1]-a[1])**2)**.5)
        distance=abs((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0]))/length
        return distance<.1 and min(a[0],b[0])-.1<=point[0]<=max(a[0],b[0])+.1 and min(a[1],b[1])-.1<=point[1]<=max(a[1],b[1])+.1
    with fitz.open(stream=pdf,filetype='pdf') as document:
        for page in document:
            for annotation in page.annots() or []:
                record=by_name.get(annotation.info.get('id'))
                if not record:continue
                sheet=by_sheet[record['sheet_id']];regions=sheet['protected_regions']
                if annotation.type[1] in ('Line','PolyLine'):
                    vertices=annotation.vertices
                    for a,b in zip(vertices,vertices[1:]):
                        for region in regions:
                            if not _segment_crosses_rect(a,b,region['bbox']):continue
                            # Only an explicitly recorded thin leader may exit a
                            # real original Multiply Highlight enclosing its own
                            # source anchor. Every text/dimension/NORTH stays hard.
                            allowed=[]
                            if record['role'].startswith('leader') and region.get('multiply_highlight'):
                                allowed=[crossing for crossing in sheet.get('allowed_source_annotation_crossings',[])
                                    if crossing['annotation_nm']==region.get('source_annotation_nm') and
                                    crossing['physical_point_id']==record['physical_point_id'] and
                                    crossing['source_sha256']==sheet['source_sha256'] and
                                    not crossing['original_annotation_modified'] and
                                    crossing['policy']=='THIN_NO_FILL_LEADER_EXIT_FROM_ORIGINAL_MULTIPLY_HIGHLIGHT_ENCLOSING_SOURCE_ANCHOR' and
                                    on_segment(a,crossing['segment']) and on_segment(b,crossing['segment'])]
                            assert allowed,(record['role'],record['physical_point_id'],region['kind'],region.get('id'))
                            for crossing in allowed:
                                original=originals[sheet['page_index']][crossing['annotation_nm']]
                                assert original=={'type':'Ink','subject':'Highlight','blend':('name','/Multiply')}
                else:
                    assert not any(annotation.rect.intersects(fitz.Rect(region['bbox'])) for region in regions),(record['role'],record['physical_point_id'])


def _verify_and_edit_every_native_object(pdf,manifest,point_ids,source_hashes):
    """Change every generated object, keeping all original content streams."""
    by_name={row['name']:row for row in manifest}
    assert len(by_name)==len(manifest) and by_name
    roles={row['role'] for row in manifest}
    assert {'bubble','number','point-warning','draft-status','schedule-border'}<=roles
    assert any(role.startswith('leader') for role in roles)
    assert AXIS_ROLES|MOMENT_ROLES<=roles
    assert any(role.startswith('schedule-row-') for role in roles)
    for row in manifest:
        assert 'physical_point_id' in row
        if row['role'] in POINT_ROLES or row['role'].startswith('leader'):assert row['physical_point_id'] in point_ids
    original_streams=[];original_raw_streams=[]
    with fitz.open(SOURCE) as source:
        for page in source:
            original_streams.append([source.xref_stream(xref) for xref in page.get_contents()])
            original_raw_streams.append([source.xref_stream_raw(xref) for xref in page.get_contents()])
    edited=set();types=set();original_annotation_ids=[]
    with fitz.open(stream=pdf,filetype='pdf') as document:
        assert len(document)==2
        for page in document:
            assert content_hash(page)==source_hashes[page.number]
            assert [document.xref_stream(xref) for xref in page.get_contents()]==original_streams[page.number]
            assert [document.xref_stream_raw(xref) for xref in page.get_contents()]==original_raw_streams[page.number]
            source_ids=[]
            for annotation in page.annots() or []:
                name=annotation.info.get('id')
                if name not in by_name:
                    source_ids.append((name,annotation.type[1],annotation.info.get('content','')))
                    continue
                row=by_name[name];edited.add(name);types.add(annotation.type[1])
                assert annotation.type[1]==row['type']
                if row['role']=='bubble' or row['role'].startswith('leader'):
                    color=annotation.colors.get('stroke')
                    assert color and color[2]>color[0] and color[2]>color[1],('Expected blue unproved source point',row['role'])
                assert all(abs(a-b)<.1 for a,b in zip(annotation.rect,row['rect']))
                annotation.set_info(title='DISPOSABLE SOFTWARE ROUNDTRIP',subject=annotation.info.get('subject',''))
                if annotation.type[1]=='FreeText':
                    annotation.set_info(content='SOFTWARE EDIT: '+annotation.info.get('content',''))
                    annotation.update(text_color=(.23,.14,.65))
                else:
                    annotation.set_colors(stroke=(.23,.14,.65));annotation.set_border(width=1.4);annotation.set_opacity(.9);annotation.update()
            original_annotation_ids.append(source_ids)
        assert edited==set(by_name)
        assert {'FreeText','Circle','Square'}<=types and bool(types&{'Line','PolyLine'})
        saved=document.tobytes(garbage=4,deflate=True)
    # Reopen, inspect every edit and /NM identity, save again, reopen again.
    with fitz.open(stream=saved,filetype='pdf') as reopened:
        seen=set()
        for page in reopened:
            retained=[]
            for annotation in page.annots() or []:
                name=annotation.info.get('id')
                if name not in by_name:
                    retained.append((name,annotation.type[1],annotation.info.get('content','')));continue
                seen.add(name)
                assert annotation.info['title']=='DISPOSABLE SOFTWARE ROUNDTRIP'
                assert annotation.type[1]==by_name[name]['type']
                if annotation.type[1]=='FreeText':assert annotation.info['content'].startswith('SOFTWARE EDIT: ')
                else:assert abs(annotation.border['width']-1.4)<.001
            assert retained==original_annotation_ids[page.number]
            assert [reopened.xref_stream(xref) for xref in page.get_contents()]==original_streams[page.number]
            assert [reopened.xref_stream_raw(xref) for xref in page.get_contents()]==original_raw_streams[page.number]
        assert seen==edited
        twice=reopened.tobytes(garbage=3,deflate=True)
    with fitz.open(stream=twice,filetype='pdf') as reopened:
        assert Counter(a.info.get('id') for page in reopened for a in page.annots() or [] if a.info.get('id') in by_name)==Counter({name:1 for name in by_name})
        for page in reopened:
            assert [reopened.xref_stream(xref) for xref in page.get_contents()]==original_streams[page.number]
            assert [reopened.xref_stream_raw(xref) for xref in page.get_contents()]==original_raw_streams[page.number]
    return roles


def exercise_real_pdf_layout(page,context,base):
    response=context.request.post(base+'/api/v1/projects',data={
        'title':'1010 native layout — DISPOSABLE SOFTWARE VALIDATION','line_id':LINE})
    assert response.ok,response.text();p=response.json();project=base+'/api/v1/projects/'+p['id']
    response=context.request.post(project+'/sources?version=1',multipart={
        'file':{'name':SOURCE.name,'mimeType':'application/pdf','buffer':SOURCE.read_bytes()}})
    assert response.ok,response.text();p=response.json()
    response=context.request.post(project+'/physical-model/source-points',data={'version':p['version'],'confirmed':True})
    assert response.ok,response.text();p=response.json()
    assert len(p['nodes'])==47 and all(n['station_mm'] is None and n['number'] is None and n['route'] is None for n in p['nodes'])
    point_ids={n['id'] for n in p['nodes']};original_nodes=p['nodes'];original_graph=p['graph']
    point_evidence={n['id']:{key:n.get(key) for key in ('station_mm','number','route','order','reasons','evidence','source_observation','source_observations')} for n in p['nodes']}
    source_hashes=[sheet['content_hash'] for sheet in p['sheets']]
    page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
    page.get_by_role('button',name='Review native PDF layout',exact=True).click()
    dialog=page.get_by_role('dialog',name='Native PDF layout review',exact=True)
    expect(dialog.get_by_label('Current graphical review state',exact=True)).to_contain_text('has not been accepted')
    with page.expect_response(lambda r:'/pdf-layout/preview' in r.url and r.request.method=='POST') as proposed:
        dialog.get_by_role('button',name='Generate native layout preview',exact=True).click()
    assert proposed.value.ok,proposed.value.text();report=proposed.value.json()
    if not report['can_export']:
        blocked={issue.get('object_key','').split(':')[-1] for issue in report.get('issues',[])}
        diagnostic={'summary':report['summary'],'issues':report.get('issues'),
            'blocked_points':[{'point_id':n['id'],'review_label':n.get('review_label'),'source_observation':n.get('source_observation'),
                'instances':n['instances']} for n in p['nodes'] if n['id'] in blocked]}
        Path('/tmp/real-1010-native-layout-blocked.json').write_text(json.dumps(diagnostic,indent=2))
    assert report['can_export'],report.get('issues')
    assert report['summary']['point_instances']==47 and len(report['sheets'])==2
    assert report['summary']['protected_regions']>0 and report['summary']['layout_exceptions']==0
    positions=[position for sheet in report['sheets'] for position in sheet['point_positions']]
    assert len(positions)==47 and {position['physical_point_id'] for position in positions}==point_ids
    assert all(sheet['north_regions'] and sheet['axis'] and sheet['schedule'] for sheet in report['sheets'])
    assert context.request.get(project).json()['nodes']==original_nodes
    wait_for_drawing(page,'.pdf-preview canvas')
    expect(dialog.get_by_label('Confirm graphical placement review only',exact=True)).to_be_disabled()
    canvas=dialog.get_by_label('Generated PDF page',exact=True)
    width=canvas.evaluate('(canvas)=>canvas.width')
    dialog.get_by_role('button',name='Zoom in native PDF',exact=True).click();wait_for_drawing(page,'.pdf-preview canvas')
    assert canvas.evaluate('(canvas)=>canvas.width')>width
    dialog.get_by_role('button',name='Fit native PDF width',exact=True).click();wait_for_drawing(page,'.pdf-preview canvas')
    dialog.get_by_role('button',name='Next preview page',exact=True).click();wait_for_drawing(page,'.pdf-preview canvas')
    expect(dialog.get_by_label('Confirm graphical placement review only',exact=True)).to_be_enabled()
    with page.expect_download() as downloaded:
        dialog.get_by_role('link',name='Download native preview PDF',exact=True).click()
    pdf=Path(downloaded.value.path()).read_bytes()
    manifest_url=urljoin(base+'/',dialog.get_by_role('link',name='Download annotation manifest',exact=True).get_attribute('href'))
    response=context.request.get(manifest_url)
    assert response.ok,response.text();manifest=_manifest_rows(response.json())
    _check_source_clearance(pdf,manifest,report)
    roles=_verify_and_edit_every_native_object(pdf,manifest,point_ids,source_hashes)
    assert len(manifest)==report['summary']['generated_objects']
    page.screenshot(path='/tmp/caesar-screens/real-1010-native-layout-preview.png',full_page=True)
    dialog.get_by_label('Graphical layout review evidence',exact=True).fill(
        'DISPOSABLE SOFTWARE VALIDATION ONLY: inspect both actual native preview sheets, source dimensions/materials/NORTH clearance, individual blue point labels/leaders/warnings, axis/moment objects and per-sheet schedules. Accept graphic placement only; no station, physical topology, XYZ or engineering issue is approved.')
    dialog.get_by_label('Confirm graphical placement review only',exact=True).check()
    with page.expect_response(lambda r:'/pdf-layout/accept' in r.url and r.request.method=='POST') as accepted:
        dialog.get_by_role('button',name='Accept graphical placements',exact=True).click()
    assert accepted.value.ok,accepted.value.text();expect(dialog).not_to_be_visible()
    p=context.request.get(project).json()
    assert {n['id'] for n in p['nodes']}==point_ids and p['graph']==original_graph
    assert all({key:n.get(key) for key in point_evidence[n['id']]}==point_evidence[n['id']] for n in p['nodes'])
    assert all(n['station_mm'] is None and n['number'] is None for n in p['nodes'])
    response=context.request.get(project+'/pdf-layout')
    assert response.ok,response.text();assert response.json()['accepted']['current']

    # Normal issue/export uses the reviewed graphic placement, not a separate
    # SVG approximation. It remains an engineering review draft with blue facts.
    page.get_by_role('button',name='Export review',exact=True).click()
    with page.expect_response(lambda r:'/exports' in r.url and r.request.method=='POST') as exported:
        page.get_by_role('button',name='Generate review bundle',exact=True).click()
    assert exported.value.ok,exported.value.text()
    expect(page.get_by_role('button',name='Download review bundle (.zip)',exact=True)).to_be_visible(timeout=30000)
    with page.expect_download() as downloaded:
        page.get_by_role('button',name='Download review bundle (.zip)',exact=True).click()
    with zipfile.ZipFile(io.BytesIO(Path(downloaded.value.path()).read_bytes())) as archive:
        output_manifest=_manifest_rows(json.loads(archive.read('annotation-manifest.json')))
        output_pdf=archive.read('annotated-review.pdf');qa=json.loads(archive.read('qa.json'))
        assert qa['source_content_unchanged'] and qa['release']=='ENGINEERING_REVIEW_DRAFT'
        output_roles=_verify_and_edit_every_native_object(output_pdf,output_manifest,point_ids,source_hashes)
        assert output_roles==roles
        def placement_map(rows):return {(r['sheet_id'],r['group'],r['role']):r['rect'] for r in rows}
        assert placement_map(output_manifest)==placement_map(manifest)
        assert all(n['station_mm'] is None and n['number'] is None for n in json.loads(archive.read('project.json'))['nodes'])
    page.get_by_role('button',name='Preview generated PDF',exact=True).click()
    wait_for_drawing(page,'.pdf-preview canvas')
    expect(page.get_by_role('dialog',name='Generated review PDF',exact=True)).to_be_visible()
    page.get_by_role('button',name='Close dialog',exact=True).click()
    print('PASS: exact47-source-point whole-project native preview, protected NORTH/dimensions/materials, explicit graphical-only accept, identical exported placements, all axis/moment/schedule/point/blue-warning/draft native objects edited and reopened twice with byte-identical original streams; unknown engineering facts unchanged.',flush=True)
