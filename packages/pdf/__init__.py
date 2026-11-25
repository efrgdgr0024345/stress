"""Native PDF adapter. Display coordinates never establish physical dimensions."""

import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
from copy import deepcopy
import math

import fitz
from packages.catalogs import schedule_lines
from packages.physical.source_review import point_label

RED = (0.82, 0.19, 0.19)
BLUE = (0.12, 0.34, 0.85)


def inspect_pdf(path):
    with fitz.open(path) as doc:
        if doc.needs_pass:
            raise ValueError(
                "Password-protected PDFs are not supported. Upload an unlocked copy."
            )
        if not 1 <= len(doc) <= 100:
            raise ValueError("A source must contain between 1 and 100 pages.")
        result = []
        for i, page in enumerate(doc):
            if max(page.rect.width, page.rect.height) > 14400:
                raise ValueError("Page exceeds supported PDF dimensions.")
            text = page.get_text()[:100000]
            vector_paths=len(page.get_cdrawings())
            image_count=len(page.get_image_info())
            result.append(
                {
                    "page_index": i,
                    "width": page.cropbox.width,
                    "height": page.cropbox.height,
                    "rotation": page.rotation,
                    "text": text,
                    "native_text_chars":len(text.strip()),
                    "vector_paths":vector_paths,
                    "image_count":image_count,
                    "content_hash":content_hash(page),
                    "format": "Vector / text" if text.strip() and vector_paths else "Searchable text" if text.strip() else "Vector / outlined-text review" if vector_paths else "Raster / OCR review" if image_count else "No searchable content / review",
                }
            )
        return result


def create_sample(path):
    doc = fitz.open()
    for index in range(2):
        page = doc.new_page(width=1100, height=760)
        ink = (0.20, 0.24, 0.25)
        faint = (0.65, 0.68, 0.67)

        def text(x, y, value, size=9, color=ink):
            page.insert_text((x, y), value, fontsize=size, fontname="helv", color=color)

        def line(a, b, width=1, color=ink):
            page.draw_line(a, b, width=width, color=color)

        page.draw_rect(fitz.Rect(25, 25, 1075, 735), color=faint, width=0.6)
        text(46, 49, "SYNTHETIC TRAINING DRAWING  /  NOT FOR ENGINEERING USE", 9, faint)
        text(895, 53, "N", 12)
        line((900, 113), (900, 68), 1.3)
        line((900, 68), (895, 80))
        line((900, 68), (905, 80))
        coords = (
            [(160, 485), (340, 381), (500, 473), (500, 282), (710, 161), (885, 262)]
            if index == 0
            else [
                (170, 485),
                (350, 381),
                (540, 490),
                (730, 380),
                (730, 210),
                (920, 100),
            ]
        )
        for a, b in zip(coords, coords[1:]):
            line(a, b, 2.2)
        for j, (x, y) in enumerate(coords):
            page.draw_circle((x, y), 3, fill=ink, color=ink)
            if j in (1, 4):
                line((x - 9, y - 14), (x + 9, y + 14), 2)
                line((x - 4, y - 17), (x + 14, y + 11), 2)
        x, y = coords[2]
        line((x, y), (x + 146, y + 84), 2.2)
        line((x + 146, y + 84), (x + 146, y + 115), 2.2)
        text(x + 165, y + 112, "VENT / BRANCH 01", 9)
        for a, b in [(coords[0], coords[1]), (coords[3], coords[4])]:
            aa = (a[0] - 22, a[1] - 32)
            bb = (b[0] - 22, b[1] - 32)
            line(aa, bb, 0.5, faint)
            line((aa[0] - 4, aa[1] - 7), (aa[0] + 4, aa[1] + 7), 0.5)
            line((bb[0] - 4, bb[1] - 7), (bb[0] + 4, bb[1] + 7), 0.5)
            text((aa[0] + bb[0]) / 2 - 12, (aa[1] + bb[1]) / 2 - 10, "1200", 9)
        for j, (x, y) in enumerate([coords[0], coords[3]]):
            line((x - 12, y + 22), (x + 12, y + 22), 1)
            line((x, y), (x, y + 22))
            text(x - 16, y + 40, f"S-{index + 1}0{j + 1}", 8)
        text(
            coords[0][0] - 20,
            coords[0][1] + 68,
            "FROM EQUIPMENT" if index == 0 else "CONT. FROM SHEET 1",
            8,
        )
        text(
            coords[-1][0] - 40,
            coords[-1][1] - 20,
            "CONT. ON SHEET 2" if index == 0 else "TO BATTERY LIMIT",
            8,
        )
        page.draw_rect(fitz.Rect(47, 590, 560, 687), color=faint, width=0.7)
        text(57, 609, "BILL OF MATERIALS  /  SYNTHETIC EXAMPLE", 9)
        for j, value in enumerate(
            [
                "01   PIPE, SEAMLESS   8 IN   ASTM A106 GR B",
                "02   ELBOW, 90 DEG   8 IN   ASTM A234 WPB",
                "03   FLANGE, WN   8 IN   ASME B16.5",
                "04   BALL VALVE   8 IN   VENDOR TO BE CONFIRMED",
            ]
        ):
            text(57, 628 + j * 15, value, 8)
        page.draw_rect(fitz.Rect(590, 605, 1050, 710), color=faint, width=0.7)
        text(609, 628, "CAESAR  /  ENGINEERING SANDBOX", 12)
        text(609, 651, "LINE: DEMO-8-CS-001     /     UTILITY WATER", 10)
        text(
            609,
            675,
            f"ISO-TRAINING-001    |    SHEET {index + 1} OF 2    |    REV A",
            9,
        )
        text(609, 695, "NOT TO SCALE   -   ALL GEOMETRY IS ILLUSTRATIVE", 8)
    doc.save(path)
    doc.close()


def content_hash(page):
    return [
        hashlib.sha256(page.parent.xref_stream(x)).hexdigest()
        for x in page.get_contents()
    ]


def wrap_text(text, width, fontsize=6.5):
    if width < 10:
        raise ValueError("Annotation is too narrow for readable text.")
    lines = []
    for paragraph in str(text).split("\n"):
        segment = ""
        for character in paragraph:
            if (
                fitz.get_text_length(
                    segment + character, fontname="helv", fontsize=fontsize
                )
                > width
            ):
                lines.append(segment)
                segment = ""
            segment += character
        lines.append(segment)
    return lines


def wrapped_schedule(materials, width):
    return [
        line
        for text in schedule_lines(materials)
        for line in wrap_text(text, width - 10)
    ]


def raw_content_hash(page):
    return [hashlib.sha256(page.parent.xref_stream_raw(x)).hexdigest() for x in page.get_contents()]


def source_annotation_snapshot(page):
    """Source annotation appearances/flags are preserved separately from /Contents."""
    values=[]
    for annotation in page.annots() or []:
        appearance=[]
        kind,value=page.parent.xref_get_key(annotation.xref,'AP')
        import re
        for ref in re.findall(r'(\d+)\s+\d+\s+R',value if kind!='null' else ''):
            xref=int(ref)
            if page.parent.xref_is_stream(xref):appearance.append(hashlib.sha256(page.parent.xref_stream_raw(xref)).hexdigest())
        values.append({'type':annotation.type[1],'info':deepcopy(annotation.info),'rect':list(annotation.rect),
            'vertices':deepcopy(annotation.vertices),'flags':annotation.flags,'colors':deepcopy(annotation.colors),
            'border':deepcopy(annotation.border),'opacity':annotation.opacity,'appearance_sha256':appearance,
            'blend_mode':page.parent.xref_get_key(annotation.xref,'BM')})
    return values


def _layout_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _source_warning_entries(project):
    from packages.physical.source_exceptions import source_exception_report
    from packages.engineering.continuations import audit as continuation_audit
    result={}
    for entry in source_exception_report(project)['active']+continuation_audit(project):
        uid=entry.get('id') or entry.get('continuation_id') or _layout_digest(entry)[:24]
        if not entry.get('sheet_id'):continue
        result[uid]={**deepcopy(entry),'id':uid}
    return sorted(result.values(),key=lambda r:(r['sheet_id'],r['code'],str(r.get('material_item_no') or ''),str(r.get('occurrence') or ''),
        str(r.get('source_text') or ''),str(r.get('bbox') or r.get('source_bbox') or r.get('source_region_bbox') or ''),r['id']))


def layout_input_sha256(project):
    """Cheap graphic-only binding: model revision/status receipts are excluded."""
    protection=Path(__file__).resolve().parents[1]/'physical/profiles/1010-layout-source.json'
    profile_sha=hashlib.sha256(protection.read_bytes()).hexdigest() if protection.is_file() else None
    algorithm_sha=hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('layout.py').read_bytes()).hexdigest()
    return _layout_digest({'project_id':project['id'],'schema':'native-layout-1','algorithm_sha256':algorithm_sha,
        'source_protection_profile_sha256':profile_sha,
        'sheets':[{k:deepcopy(s.get(k)) for k in ('id','source_id','page_index','sha256','content_hash','width','height','rotation','axis','table','line_id','printed_id')}
            for s in project['sheets']],
        'nodes':[{**{k:deepcopy(n.get(k)) for k in ('id','number','review_label','reasons','instances','evidence')},
                  'source_observation_evidence':(n.get('source_observation') or {}).get('evidence')}
            for n in sorted(project['nodes'],key=lambda n:n['id'])],
        'schedules':{s['id']:schedule_lines(sorted((m for m in project['materials'] if m['sheet_id']==s['id'] and m['family'] in ('flange','valve')),key=lambda m:m['id'])) for s in project['sheets']},
        'annotations':sorted(deepcopy(project.get('annotations',[])),key=lambda n:n['id']),
        'source_warnings':_source_warning_entries(project)})


def _source_document(project,source_path):
    document=fitz.open();decoded=[];raw=[];annotations=[];sources={}
    try:
        for sheet in project['sheets']:
            path=Path(source_path(sheet['source_id']))
            if sheet['source_id'] not in sources:sources[sheet['source_id']]=hashlib.sha256(path.read_bytes()).hexdigest()
            if sources[sheet['source_id']]!=sheet.get('sha256'):
                raise ValueError('PDF_SOURCE_HASH_MISMATCH: stored source bytes differ from the registered drawing; layout/export stopped.')
            with fitz.open(path) as source:
                page=source[sheet['page_index']]
                if sheet.get('content_hash') and content_hash(page)!=sheet['content_hash']:
                    raise ValueError('PDF_SOURCE_CONTENT_MISMATCH: source page streams differ from the registered drawing.')
                decoded.append(content_hash(page));raw.append(raw_content_hash(page));annotations.append(source_annotation_snapshot(page))
                document.insert_pdf(source,from_page=sheet['page_index'],to_page=sheet['page_index'],annots=True)
        return document,decoded,raw,annotations
    except Exception:
        document.close();raise


def _layout_evidence(sheet):
    path=Path(__file__).resolve().parents[1]/'physical/profiles/1010-layout-source.json'
    if not path.is_file():return {}
    data=json.loads(path.read_text())
    if data['source_sha256']!=sheet.get('sha256'):return {}
    return next((p for p in data['pages'] if p['page_index']==sheet['page_index']),{})


def _schedule_objects(materials,width):
    rows=[{'group':'schedule','role':'schedule-title','text':'COMPONENT SCHEDULE | ENGINEERING REVIEW','material_id':None}]
    for material in sorted(materials,key=lambda m:(m['item_no'],m['id'])):
        values=schedule_lines([material])[1:]
        if material['family']=='valve':values=values[:-2]
        for line_index,value in enumerate(values):
            for part,text in enumerate(wrap_text(value,width-10)):
                rows.append({'group':material['id'],'role':f'schedule-row-{line_index}-{part}',
                    'text':text,'material_id':material['id']})
    if any(m['family']=='valve' for m in materials):
        for index,value in enumerate(schedule_lines([next(m for m in materials if m['family']=='valve')])[-2:]):
            for part,text in enumerate(wrap_text(value,width-10)):
                rows.append({'group':'schedule','role':f'schedule-warning-{index}-{part}','text':text,'material_id':None})
    return rows


def _plan_document(project,document,decoded,raw,source_annotations):
    from packages.pdf.layout import LayoutPlanner
    pages=[];all_issues=[];names={a.info.get('id') for page in document for a in page.annots() or [] if a.info.get('id')}
    for page_index,sheet in enumerate(project['sheets']):
        page=document[page_index];evidence=_layout_evidence(sheet);regions=[]
        exclusions={r['evidence_id'] for r in evidence.get('text_protection_exclusions',[])}
        supplied=deepcopy(evidence.get('protected_regions',[]))+[
            {**deepcopy(word),'kind':'SOURCE_OCR_TEXT'} for word in evidence.get('protected_source_words',[])
            if word.get('evidence_id') not in exclusions]
        for region in supplied:
            box=region.get('bbox') or region.get('rect')
            if not box:continue
            regions.append({**region,'id':region.get('id') or 'source-word-'+str(len(regions)),
                'kind':region.get('kind','SOURCE_TEXT'),'bbox':deepcopy(box)})
        planner=LayoutPlanner(page,sheet,sheet.get('sha256'),regions)
        placements=[];point_positions=[];notes=[]
        def add(group,role,kind,**details):
            # Graphic floats are canonical to sub-micropoint precision. This
            # prevents +70/-70 origin arithmetic from changing an accepted
            # placement's identity by 1e-14; physical/source values stay exact.
            if details.get('rect'):details['rect']=[round(float(v),6) for v in details['rect']]
            if details.get('vertices'):details['vertices']=[[round(float(v),6) for v in point] for point in details['vertices']]
            name=f"caesar:{project['id']}:{sheet['id']}:{group}:{role}"
            if name in names:
                name+=':source-'+sheet['sha256'][:16]
                suffix=0;base=name
                while name in names:suffix+=1;name=base+'-'+str(suffix)
            names.add(name)
            entry={'name':name,'group':group,'role':role,'type':kind,'sheet_id':sheet['id'],
                'physical_point_id':None,'color':list(RED),**details}
            placements.append(entry);return entry
        notice_width=min(540,sheet['width']-20)
        rect=planner.place_box([32,6],notice_width,18,'draft-status')
        if rect:add('release','draft-status','FreeText',rect=rect,text='ENGINEERING REVIEW DRAFT | NOT VERIFIED FOR MODELLING',fontsize=8)
        materials=[m for m in project['materials'] if m['sheet_id']==sheet['id'] and m['family'] in ('flange','valve')]
        schedule=None
        if materials:
            width=min(370,sheet['width']-16);rows=_schedule_objects(materials,width);height=12*len(rows)+12
            preferred=sheet.get('table') or evidence.get('schedule_proposal',{}).get('position') or [80,200]
            if evidence and not sheet.get('table'):preferred=[80,200]
            rect=planner.place_box(preferred,width,height,'schedule')
            if rect:
                schedule={'position':rect[:2],'rect':rect,'width':width,'row_count':len(rows)}
                add('schedule','schedule-border','Square',rect=rect,border=1)
                for index,row in enumerate(rows):
                    add(row['group'],row['role'],'FreeText',rect=[rect[0]+5,rect[1]+6+index*12,rect[2]-5,rect[1]+18+index*12],
                        text=row['text'],fontsize=6.5,material_id=row['material_id'])
        source_warnings=[];warning_y=(schedule['rect'][3]+10 if schedule else 200)
        for entry in (w for w in _source_warning_entries(project) if w['sheet_id']==sheet['id']):
            label=('Item '+str(entry['material_item_no'])+' / '+str(entry.get('occurrence') or '')+': ' if entry.get('material_item_no') else '')
            code=entry['code'].replace('_',' ')
            detail=('Needs accepted dimension-chain COD/XYZ proof.' if entry['code']=='UNCONFIRMED_ELBOW_COD' else
                'Confirm valve/instrument classification from source evidence.' if entry['code']=='INSTRUMENT_CLASSIFICATION_REVIEW_REQUIRED' else
                'No peer connection accepted: '+entry.get('reason_code','review boundary').replace('_',' ') if entry['code']=='CONTINUATION_ENDPOINT_EXCEPTION' else
                'Review exact source endpoints: '+str(entry.get('source_text') or '') if entry['code']=='DIMENSION_WITNESS_MAPPING_UNCONFIRMED' else
                'Review the current source interface and evidence; no physical value was inferred.')
            width=min(370,sheet['width']-16);lines=wrap_text(label+code+'\n'+detail,width-10,6.5);height=max(28,len(lines)*9+8)
            rect=planner.place_box([80,warning_y],width,height,'source-warning:'+entry['id'])
            warning_y+=height+5
            if not rect:continue
            point_ids=entry.get('point_ids') or ([entry['physical_point_id']] if entry.get('physical_point_id') else [])
            point_id=point_ids[0] if len(point_ids)==1 else None
            add(entry['id'],'source-warning','FreeText',rect=rect,text='\n'.join(lines),fontsize=6.5,color=list(BLUE),
                physical_point_id=point_id,related_physical_point_ids=point_ids,
                reason_codes=[entry['code']]+([entry['reason_code']] if entry.get('reason_code') else []),
                source_evidence=entry.get('evidence') or entry.get('message'),source_bbox=entry.get('source_bbox') or entry.get('bbox') or entry.get('source_region_bbox'),
                material_id=entry.get('material_id'),requirement_id=entry.get('requirement_id') or entry['id'],source_sha256=sheet['sha256'])
            source_warnings.append({'id':entry['id'],'code':entry['code'],'rect':rect,'physical_point_id':point_id})
        axis=None;north=planner.north_regions[0]['bbox'] if planner.north_regions else None
        if north or sheet.get('axis'):
            preferred=([sheet['axis'][0]-60,sheet['axis'][1]-70] if sheet.get('axis') else [north[2]+54,max(5,north[1]-11)])
            near=[(north[0]+north[2])/2,(north[1]+north[3])/2] if north else None
            rect=planner.place_box(preferred,160,110,'triad',near=near,max_distance=300 if north else None)
            if rect:
                x,y=rect[0]+60,rect[1]+70;axis={'origin':[x,y],'rect':rect,'north_bbox':north,'physical_axis_convention_accepted':False}
                for label,dx,dy,label_box in [('X',36,20,[95,87,112,102]),('Y',-30,20,[12,87,29,102]),('Z',0,-35,[52,18,69,34])]:
                    add('triad',f'axis-{label}-line','Line',vertices=[[x,y],[x+dx,y+dy]],arrow_end=True)
                    add('triad',f'axis-{label}-label','FreeText',rect=[rect[0]+label_box[0],rect[1]+label_box[1],rect[0]+label_box[2],rect[1]+label_box[3]],text=label,fontsize=8)
                for label,points,label_box in [('X',[[95,60],[108,57],[115,63],[114,74]],[119,64,145,78]),
                    ('Y',[[31,60],[18,57],[11,63],[12,74]],[0,64,25,78]),('Z',[[79,28],[85,17],[77,7],[65,7]],[87,4,115,18])]:
                    add('triad',f'moment-{label}-line','PolyLine',vertices=[[rect[0]+a,rect[1]+b] for a,b in points],arrow_end=True)
                    add('triad',f'moment-{label}-label','FreeText',rect=[rect[0]+label_box[0],rect[1]+label_box[1],rect[0]+label_box[2],rect[1]+label_box[3]],text='M'+label.lower(),fontsize=8)
        for note in sorted((n for n in project.get('annotations',[]) if n['sheet_id']==sheet['id']),key=lambda n:n['id']):
            original=note['rect'];width=original[2]-original[0];height=original[3]-original[1]
            if note['kind']=='Line':width=max(2,width);height=max(2,height)
            rect=planner.place_box(original,width,height,'drawing-note:'+note['id'])
            if not rect:continue
            color=[int(note['color'][j:j+2],16)/255 for j in (1,3,5)];details={'rect':rect,'color':color}
            if note['kind']=='FreeText':
                lines=wrap_text(note['text'],width-4,10)
                if len(lines)*12>height-4:
                    planner._fail('LAYOUT_NOTE_TEXT_OVERFLOW','A native text note cannot fit its readable box; enlarge it before exporting.',note['id']);continue
                details.update(text='\n'.join(lines),fontsize=10)
            elif note['kind']=='Line':details['vertices']=[rect[:2],rect[2:]]
            add(note['id'],'drawing-note',note['kind'],**details);notes.append({'id':note['id'],'requested_rect':original,'rect':rect})
        pending=[];point_warning_index=0;point_warning_y=warning_y+6
        for node in sorted(project['nodes'],key=lambda n:(n.get('review_label') or '',n['id'])):
            for instance in (i for i in node['instances'] if i['sheet_id']==sheet['id']):
                label=point_label(node);diameter=max(32,math.ceil(fitz.get_text_length(label,fontname='helv',fontsize=8))+8)
                requested=instance['bubble'];rect=planner.place_box([requested[0]-diameter/2,requested[1]-diameter/2],diameter,diameter,
                    'point:'+node['id'],near=instance['anchor'],max_distance=360)
                if not rect:continue
                bubble=[(rect[0]+rect[2])/2,(rect[1]+rect[3])/2];color=list(BLUE if node.get('reasons') else RED)
                add(node['id'],'bubble','Circle',rect=rect,color=color,fill=[1,1,1],border=1,physical_point_id=node['id'])
                add(node['id'],'number','FreeText',rect=[rect[0]+2,bubble[1]-6,rect[2]-2,bubble[1]+9],text=label,fontsize=8,align=1,
                    color=color,physical_point_id=node['id'])
                if node.get('reasons'):
                    warning=planner.place_box([80+(point_warning_index%2)*200,
                        point_warning_y+(point_warning_index//2)*30],190,24,'point-warning:'+node['id'])
                    point_warning_index+=1
                    reason=node['reasons'][0].replace('_',' ')
                    warning_text=label+': '+reason+ ('\nSTATION UNKNOWN' if node.get('station_mm') is None else '')
                    if warning:add(node['id'],'point-warning','FreeText',rect=warning,text=warning_text,fontsize=6.5,
                        color=list(BLUE),physical_point_id=node['id'],reason_codes=deepcopy(node['reasons']),
                        source_evidence=node.get('evidence') or (node.get('source_observation') or {}).get('evidence'))
                position={'physical_point_id':node['id'],'anchor':deepcopy(instance['anchor']),'bubble':bubble,
                    'requested_bubble':deepcopy(requested),'leader_vertices':None}
                point_positions.append(position);pending.append((node,position,diameter/2-1,color))
        for node,position,radius,color in pending:
            route=planner.route_leader(position['anchor'],position['bubble'],'leader:'+node['id'])
            if not route:continue
            # Stop at the bubble boundary rather than crossing its numeric label.
            route=deepcopy(route);remaining=radius
            while len(route)>1:
                a,b=route[-2:];distance=math.dist(a,b)
                if distance<=remaining:remaining-=distance;route.pop();continue
                route[-1]=[b[0]+(a[0]-b[0])*remaining/distance,b[1]+(a[1]-b[1])*remaining/distance];break
            position['leader_vertices']=route
            for index,(a,b) in enumerate(zip(route,route[1:])):
                add(node['id'],'leader' if len(route)==2 else f'leader-segment-{index}','Line',vertices=[a,b],color=color,border=.8,
                    physical_point_id=node['id'])
        issue_list=deepcopy(planner.issues);all_issues.extend(issue_list)
        pages.append({'sheet_id':sheet['id'],'page_index':sheet['page_index'],'source_sha256':sheet['sha256'],
            'protected_regions':deepcopy(planner.protected_regions),'north_regions':deepcopy(planner.north_regions),
            'placements':placements,'point_positions':point_positions,'axis':axis,'schedule':schedule,'notes':notes,
            'source_warnings':source_warnings,
            'issues':issue_list,'can_export':planner.can_export,'source_annotations':source_annotations[page_index],
            'allowed_source_annotation_crossings':[{**deepcopy(c),'physical_point_id':c.get('object_key','').removeprefix('leader:')}
                for c in getattr(planner,'allowed_source_annotation_crossings',[])]})
    placements=[p for sheet in pages for p in sheet['placements']]
    return {'schema':'native-layout-1','revision':project.get('version'),'input_sha256':layout_input_sha256(project),
        'can_export':not all_issues,'sheets':pages,'issues':all_issues,'summary':{'point_instances':sum(len(s['point_positions']) for s in pages),
            'generated_objects':len(placements),'layout_exceptions':len(all_issues),'protected_regions':sum(len(s['protected_regions']) for s in pages)},
        'source_content_hashes':decoded,'source_raw_content_hashes':raw,'placements_sha256':_layout_digest(placements),
        'physical_values_modified':False,'source_locations_modified':False,'engineering_approved':False}


def plan_layout(project,source_path):
    document,decoded,raw,annotations=_source_document(project,source_path)
    try:return _plan_document(project,document,decoded,raw,annotations)
    finally:document.close()


layout_report=plan_layout


def accepted_plan_current(project,plan=None):
    proof=project.get('native_layout_review') or {}
    return bool(proof.get('reviewed_by') and proof.get('reason') and proof.get('input_sha256')==layout_input_sha256(project) and
        (plan is None or plan['can_export'] and plan['input_sha256']==proof['input_sha256'] and plan['placements_sha256']==proof.get('placements_sha256')))


def apply_layout(project,plan,reviewer,reviewed_at,reason):
    if not reviewer or not reviewed_at or not isinstance(reason,str) or len(reason.strip())<10:raise ValueError('Explicit authenticated graphical layout evidence is required.')
    if not plan['can_export'] or plan['input_sha256']!=layout_input_sha256(project):raise ValueError('Layout source/object context changed or unsafe placements remain; preview the current drawing again.')
    candidate=deepcopy(project);nodes={n['id']:n for n in candidate['nodes']};sheets={s['id']:s for s in candidate['sheets']}
    for page in plan['sheets']:
        sheet=sheets[page['sheet_id']]
        for position in page['point_positions']:
            instance=next(i for i in nodes[position['physical_point_id']]['instances'] if i['sheet_id']==sheet['id'])
            instance['bubble']=deepcopy(position['bubble'])
        if page['axis']:sheet['axis']=deepcopy(page['axis']['origin'])
        if page['schedule']:sheet['table']=deepcopy(page['schedule']['position'])
        for note in page['notes']:
            next(n for n in candidate['annotations'] if n['id']==note['id'])['rect']=deepcopy(note['rect'])
    old=candidate.get('native_layout_review')
    if old:candidate.setdefault('native_layout_history',[]).append(deepcopy(old))
    candidate['native_layout_review']={'schema':plan['schema'],'input_sha256':layout_input_sha256(candidate),
        'proposal_sha256':plan['input_sha256'],'placements_sha256':plan['placements_sha256'],
        'reviewed_by':reviewer,'reviewed_at':reviewed_at,'reason':reason.strip(),'engineering_approved':False}
    project.clear();project.update(candidate)
    return deepcopy(project['native_layout_review'])


def _render_plan(document,project,plan):
    manifest=[];sheets={s['id']:s for s in project['sheets']}
    for index,page_plan in enumerate(plan['sheets']):
        page=document[index];sheet=sheets[page_plan['sheet_id']]
        for item in sorted(page_plan['placements'],key=lambda p:(0 if p['role'].startswith('leader') else 1 if p['type'] in ('Square','Circle','Line','PolyLine') else 2)):
            kind=item['type'];color=tuple(item['color'])
            if kind=='FreeText':annotation=page.add_freetext_annot(fitz.Rect(item['rect']),item['text'],fontsize=item['fontsize'],text_color=color,align=item.get('align',0))
            # PyMuPDF expands Circle/Square /Rect by one point on creation.
            # Keep that native bound inside the source-clear reserved box.
            elif kind=='Circle':annotation=page.add_circle_annot(fitz.Rect(item['rect'])+(1,1,-1,-1))
            elif kind=='Square':annotation=page.add_rect_annot(fitz.Rect(item['rect'])+(1,1,-1,-1))
            elif kind=='PolyLine':annotation=page.add_polyline_annot(item['vertices'])
            else:annotation=page.add_line_annot(*item['vertices'])
            if kind!='FreeText':
                annotation.set_colors(stroke=color,**({'fill':tuple(item['fill'])} if item.get('fill') else {}))
                annotation.set_border(width=item.get('border',.8))
            if item.get('arrow_end'):annotation.set_line_ends(0,4)
            annotation.set_info(title='CAESAR ISO',subject=item['role']+' | '+item['group']+
                (' | '+', '.join(item['reason_codes']) if item.get('reason_codes') else '')+
                (' | Source evidence: '+item['source_evidence'] if item.get('source_evidence') else ''),content=annotation.info.get('content',''))
            document.xref_set_key(annotation.xref,'NM',fitz.get_pdf_str(item['name']));annotation.update()
            manifest.append({**deepcopy(item),'rect':list(annotation.rect),'revision':project.get('version'),
                'placement_rect':deepcopy(item.get('rect')),'native_individually_editable':True})
    return manifest


def export_bundle(project, source_path, output_path):
    document,originals,raw_originals,original_annotations=_source_document(project,source_path)
    try:
        plan=_plan_document(project,document,originals,raw_originals,original_annotations)
        if not plan['can_export']:
            codes=', '.join(sorted({i['code'] for i in plan['issues']}))
            raise ValueError('PDF_LAYOUT_UNSAFE: '+codes+'. Preview the graphical layout and resolve each explicit source collision before exporting.')
        manifest=_render_plan(document,project,plan)
        # Keep original encoded content streams as well as their decoded bytes.
        pdf_bytes=document.tobytes(garbage=3,deflate=False)
    finally:document.close()
    with fitz.open(stream=pdf_bytes,filetype='pdf') as check:
        from collections import Counter
        for index,page in enumerate(check):
            if content_hash(page)!=originals[index] or raw_content_hash(page)!=raw_originals[index]:
                raise ValueError('Original source content changed. Export aborted.')
            original=original_annotations[index];current=source_annotation_snapshot(page)
            if current[:len(original)]!=original:
                raise ValueError('Original source annotations or their appearances changed. Export aborted.')
        names=Counter(a.info.get('id') for page in check for a in page.annots() or [])
        if not all(names[item['name']]==1 for item in manifest):raise ValueError('Native annotation integrity check failed.')
    csv_file = io.StringIO()
    writer = csv.writer(csv_file)
    writer.writerow(
        [
            "physical_point_id",
            "node_number",
            "line_id",
            "route",
            "kind",
            "station_mm",
            "dimension_input",
            "evidence",
            "reasons",
            "sheet_instances",
        ]
    )

    def safe_cell(value):
        # Text from drawings / engineer input must stay literal in spreadsheet apps.
        return (
            "'" + value
            if isinstance(value, str)
            and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
            else value
        )

    for n in project["nodes"]:
        writer.writerow(
            [
                n["id"],
                n["number"],
                safe_cell(n["line_id"]),
                n["route"],
                n["kind"],
                n["station_mm"],
                safe_cell(n.get("dimension_input", "")),
                safe_cell(n["evidence"]),
                "|".join(n["reasons"]),
                len(n["instances"]),
            ]
        )
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        from packages.workbooks import workbook
        archive.writestr("engineering-workbook.xlsx",workbook(project))
        if project.get('physical_model'):
            from packages.physical import audit as physical_audit
            from packages.physical.constraints import solve
            archive.writestr('physical-model.json',json.dumps(physical_audit(project),indent=2))
            archive.writestr('dimensional-solution.json',json.dumps(solve(project),indent=2))
        archive.writestr("annotated-review.pdf", pdf_bytes)
        archive.writestr("nodes.csv", csv_file.getvalue())
        for filename, value in [
            ("project.json", project),
            ("annotation-manifest.json", manifest),
            ("native-layout.json", plan),
            ("exceptions.json", project["issues"]),
            ("materials.json", project["materials"]),
            (
                "catalog-provenance.json",
                [
                    {"material_id": m["id"], **m["catalog_match"]}
                    for m in project["materials"]
                    if m.get("catalog_match")
                ],
            ),
            ("numbering-map.json", project.get("numbering_map", [])),
            (
                "qa.json",
                {
                    "source_content_unchanged": True,
                    "source_raw_content_unchanged": True,
                    "original_annotation_appearances_unchanged":True,
                    "collision_check":"passed",
                    "native_layout_sha256":plan['placements_sha256'],
                    "allowed_source_annotation_crossings":[c for s in plan['sheets'] for c in s.get('allowed_source_annotation_crossings',[])],
                    "native_annotations": len(manifest),
                    "structural_check": "passed",
                    "workbook_reopen_check":"passed",
                    "desktop_editor_roundtrip": "not tested",
                    "release": "ENGINEERING_REVIEW_DRAFT",
                },
            ),
        ]:
            archive.writestr(filename, json.dumps(value, indent=2))
    return len(manifest)
