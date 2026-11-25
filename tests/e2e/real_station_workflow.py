"""Actual support dimension witnesses; local datum declarations stay explicit.

Every project is disposable software validation of the exact reviewed PDF.
Station direction and local zero are test declarations, never surveyed 1010 data.
"""
from decimal import Decimal
import hashlib
import io
from pathlib import Path
from openpyxl import load_workbook
from playwright.sync_api import expect

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'
SHA='7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59'
# These are source-observation identities and native path witnesses from the
# actual reviewed PDF, not a replacement/golden physical model.
CASES=(
    ('2in','53adb8b6-6462-5aa9-a2cf-435484a305da','5f5d5bc0-0a3e-5dcd-9387-5a5345e67e1c','2"','STANDARD','50.8',0,'4226/4229, arrows4227/4230, text4232-4235'),
    ('half-inch','4fb70155-7d7c-55f8-815f-8e1acf951589','b9f3ce66-2e57-50c5-a894-5b38b2445694','1/2"','STANDARD','12.7',0,'4670/4673, arrows4671/4674, text4678-4684'),
    ('2-1-8in','90e959ad-1bba-52b7-af9f-ec74723abf35','2ce6f54e-beec-56dc-8ea6-fbfc84ecc241','2.1/8"','ISO_IN_DOT_FRACTION','53.975',1,'6086/6089, arrows6087/6090, remoteleader6093, text6094-6102'),
)


def exercise_real_stations(page,context,base):
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SHA
    for index,(case,observation_a,observation_b,source_text,source_format,expected,page_index,paths) in enumerate(CASES):
        result=context.request.post(base+'/api/v1/projects',data={
            'title':'1010 real station rule '+case+' — DISPOSABLE SOFTWARE VALIDATION',
            'line_id':'8-PG-JE3LN2-1010-FUTURE'})
        assert result.ok,result.text();p=result.json();project=base+'/api/v1/projects/'+p['id']
        result=context.request.post(project+'/sources?version=1',multipart={
            'file':{'name':SOURCE.name,'mimeType':'application/pdf','buffer':SOURCE.read_bytes()}})
        assert result.ok,result.text();p=result.json()
        page.goto(base+f"/?project={p['id']}&view=results",wait_until='domcontentloaded')
        page.get_by_role('button',name='Locate source interfaces',exact=True).click()
        expect(page.get_by_role('button',name='Refresh source review',exact=True)).to_be_visible(timeout=30000)
        p=context.request.get(project).json()
        a=next(n for n in p['nodes'] if n.get('source_observation',{}).get('id')==observation_a)
        b=next(n for n in p['nodes'] if n.get('source_observation',{}).get('id')==observation_b)
        sheet=p['sheets'][page_index]
        ids={a['id'],b['id']}
        assert all(n['station_mm'] is None for n in p['nodes']) and p['graph']['edges']==[]
        evidence=('SOFTWARE VALIDATION of the actual printed '+source_text+' support dimension; native source witnesses '+paths+
            '. The dimension is unsigned; this disposable test explicitly declares local stationing direction from '+a['review_label']+' to '+b['review_label']+'. No surveyed station is claimed.')

        # Genuine printed coordinate groups are accepted as coordinate evidence
        # at OTHER actual points. Even fully known XYZ must not manufacture a
        # station or an along-centreline length anywhere in this project.
        coordinate_ids=[]
        if index==0:
            refs=context.request.get(project+'/continuations').json()['candidates'][:2]
            for ref in refs:
                coordinate_ids.append(ref['point_id'])
                for axis,text in ref['printed_coordinate_proposals'].items():
                    response=context.request.post(project+'/physical-model/dimensions',data={
                        'version':p['version'],'kind':'COORDINATE','axis':axis,'from_point_id':ref['point_id'],
                        'source_text':text,'source_format':ref['source_format'],'tolerance_text':'0 mm',
                        'sheet_id':ref['sheet_id'],'evidence':'SOFTWARE VALIDATION: actual printed source '+axis+' coordinate '+text+'; this accepts no route station or centreline length.',
                        'confirmed':True})
                    assert response.ok,response.text();p=response.json()
            model=context.request.get(project+'/physical-model').json()
            known={r['point_id']:r['axes'] for r in model['solution']['coordinates']}
            assert all(all(value['value_mm'] is not None for value in known[uid].values()) for uid in coordinate_ids)
            assert all(n['station_mm'] is None for n in p['nodes'])
            page.reload()

        station_preview=context.request.get(project+'/physical-model/stations').json()
        proposal=next(v for v in station_preview['proposals'] if {v['from_point_id'],v['to_point_id']}==ids)
        assert proposal['source_text']==source_text and proposal['source_format']==source_format
        assert proposal['engineering_approved'] is False and proposal['origin_accepted'] is False

        def open_stations():
            page.get_by_role('button',name='Along-route stations',exact=True).click()
            dialog=page.get_by_role('dialog',name='Source along-route stations',exact=True)
            expect(dialog).to_be_visible()
            return dialog

        def fill_delta(dialog):
            if dialog.get_by_label('Printed support-gap proposal',exact=True).input_value()!=proposal['id']:
                dialog.get_by_label('Printed support-gap proposal',exact=True).select_option(proposal['id'])
            dialog.get_by_label('Station evidence type',exact=True).select_option('DELTA')
            dialog.get_by_label('From point / station point',exact=True).select_option(a['id'])
            dialog.get_by_label('To point',exact=True).select_option(b['id'])
            dialog.get_by_label('Station source drawing page',exact=True).select_option(sheet['id'])
            dialog.get_by_label('Station source number convention',exact=True).select_option(source_format)
            dialog.get_by_label('Original along-route source dimension',exact=True).fill(source_text)
            dialog.get_by_label('Declared station tolerance',exact=True).fill('0 mm')
            dialog.get_by_label('Along-route source evidence',exact=True).fill(evidence)
            dialog.get_by_label('Confirm stationing direction for the printed gap',exact=True).check()
            dialog.get_by_label('Confirm along-centreline station evidence',exact=True).check()

        dialog=open_stations()
        if index==0:
            dialog.get_by_label('Printed support-gap proposal',exact=True).select_option(proposal['id'])
            expect(dialog.get_by_label('Confirm stationing direction for the printed gap',exact=True)).not_to_be_checked()
            dialog.get_by_role('button',name='Reverse stationing direction',exact=True).click()
            expect(dialog.get_by_label('From point / station point',exact=True)).to_have_value(b['id'])
            dialog.get_by_label('Confirm stationing direction for the printed gap',exact=True).check()
            dialog.get_by_role('button',name='Reverse stationing direction',exact=True).click()
            expect(dialog.get_by_label('From point / station point',exact=True)).to_have_value(a['id'])
            expect(dialog.get_by_label('Confirm stationing direction for the printed gap',exact=True)).not_to_be_checked()
            # Editing the printed text detaches its exact source binding. This
            # equivalent-unit display is never submitted as a source reading.
            dialog.get_by_label('Original along-route source dimension',exact=True).fill('50.8 mm')
            expect(dialog.get_by_label('Printed support-gap proposal',exact=True)).to_have_value('')
            expect(dialog.get_by_label('Along-route source evidence',exact=True)).to_have_value('')
        fill_delta(dialog)
        dialog.get_by_role('button',name='Save station evidence',exact=True).click()
        expect(dialog).to_have_count(0)
        stations=context.request.get(project+'/physical-model/stations').json()
        assert not stations['solution']['can_apply']
        assert all(n['station_mm'] is None for n in context.request.get(project).json()['nodes'])
        expect(page.get_by_role('button',name='Apply station solution',exact=True)).to_be_disabled()
        assert all(r['status']=='TOPOLOGY_REQUIRED' for r in stations['solution']['points'] if r['point_id'] in ids)
        delta=next(c for c in stations['constraints'] if c['kind']=='DELTA')
        assert delta['source_proposal_id']==proposal['id']

        # Source dimensions do not assign a route. This separate, explicit
        # test-only review declares just this witnessed pair's local order.
        p=context.request.get(project).json()
        for order,original in enumerate((a,b)):
            point=next(n for n in p['nodes'] if n['id']==original['id'])
            response=context.request.patch(project+'/nodes/'+point['id'],data={
                'version':p['version'],'line_id':point['line_id'],'route':'main','order':order,
                'topology_state':'ASSIGNED','topology_confirmed':True,
                'source_location_confirmed':True,'source_location_sheet_id':sheet['id'],
                'kind':'support','dimension':'','evidence':evidence,
                'instances':point['instances']})
            assert response.ok,response.text();p=response.json()
        assert all(n['station_mm'] is None for n in p['nodes'])
        page.reload()
        # Re-review the same original dimension after the explicit route
        # declaration; no source value or graphic anchor has been moved.
        dialog=open_stations()
        dialog.get_by_label('Saved station constraint',exact=True).select_option(delta['id'])
        fill_delta(dialog)
        dialog.get_by_role('button',name='Save station evidence',exact=True).click()
        expect(dialog).to_have_count(0)
        stations=context.request.get(project+'/physical-model/stations').json()
        assert not stations['solution']['can_apply']
        assert any('RELATIVE' in r['status'] for r in stations['solution']['points'] if r['point_id'] in ids)
        expect(page.get_by_role('button',name='Apply station solution',exact=True)).to_be_disabled()

        # Explicit local zero is a declared datum, never the default value of
        # an unknown or a fabricated absolute engineering station.
        dialog=open_stations()
        dialog.get_by_label('Station evidence type',exact=True).select_option('LOCAL_ORIGIN')
        dialog.get_by_label('From point / station point',exact=True).select_option(a['id'])
        dialog.get_by_label('Station source drawing page',exact=True).select_option(sheet['id'])
        expect(dialog.get_by_label('Original along-route source dimension',exact=True)).to_have_value('0 mm')
        dialog.get_by_label('Along-route source evidence',exact=True).fill(evidence+' Explicit software-test declaration: '+a['review_label']+' is local station0, not an absolute or surveyed datum.')
        dialog.get_by_label('Explicitly declare local station datum at zero',exact=True).check()
        dialog.get_by_label('Confirm along-centreline station evidence',exact=True).check()
        dialog.get_by_role('button',name='Save station evidence',exact=True).click()
        expect(dialog).to_have_count(0)
        stations=context.request.get(project+'/physical-model/stations').json()
        assert stations['solution']['can_apply']
        solved={r['point_id']:r for r in stations['solution']['points'] if r['point_id'] in ids}
        assert all(r['can_apply'] and r['basis']=='LOCAL_ORIGIN' for r in solved.values())
        assert Decimal(solved[a['id']]['proposed_station_mm'])==0
        assert Decimal(solved[b['id']]['proposed_station_mm'])==Decimal(expected)
        assert all(n['station_mm'] is None for n in context.request.get(project).json()['nodes'])
        page.get_by_role('button',name='Apply station solution',exact=True).click()
        dialog=page.get_by_role('dialog',name='Apply along-route station solution',exact=True)
        expect(dialog).to_contain_text('Declared local datum')
        expect(dialog.locator('.station-solution-grid tbody tr')).to_have_count(2)
        dialog.get_by_label('Station decision evidence',exact=True).fill(evidence+' Apply only these two fully anchored local-datum station proposals; all other stations and geometry stay unaccepted.')
        dialog.get_by_label('Confirm station solution decision',exact=True).check()
        dialog.get_by_role('button',name='Accept proved route stations',exact=True).click()
        expect(dialog).to_have_count(0)
        p=context.request.get(project).json();by_id={n['id']:n for n in p['nodes']}
        assert Decimal(by_id[a['id']]['station_mm'])==0 and Decimal(by_id[b['id']]['station_mm'])==Decimal(expected)
        assert Decimal(by_id[b['id']]['support_gap_mm'])==Decimal(expected)
        assert 'SUPPORT_WITHIN_6_IN' in by_id[b['id']]['reasons']
        assert all(n['station_mm'] is None for n in p['nodes'] if n['id'] not in ids)
        assert all(by_id[uid]['station_mm'] is None for uid in coordinate_ids)
        model=context.request.get(project+'/physical-model').json()
        coords={r['point_id']:r['axes'] for r in model['solution']['coordinates']}
        assert all(all(value['value_mm'] is None for value in coords[uid].values()) for uid in ids)
        exported=context.request.get(project+'/results').json()['tables']
        with page.expect_download() as downloaded:
            page.get_by_role('link',name='Export Excel (.xlsx)',exact=True).click()
        book=load_workbook(io.BytesIO(Path(downloaded.value.path()).read_bytes()),read_only=True,data_only=True)
        def records(table_name):
            schema=next(t for t in exported if t['name']==table_name)
            worksheet=book[table_name]
            assert list(next(worksheet.iter_rows(min_row=5,max_row=5,values_only=True)))==[c['label'] for c in schema['columns']]
            return [dict(zip((c['key'] for c in schema['columns']),row)) for row in worksheet.iter_rows(min_row=6,values_only=True)]
        station_rows=records('Stations');stored={r['point_id']:r for r in station_rows}
        for uid,value in ((a['id'],Decimal(0)),(b['id'],Decimal(expected))):
            row=stored[uid]
            assert isinstance(row['existing_station_mm'],(int,float)) and Decimal(str(row['existing_station_mm']))==value
            assert isinstance(row['proposed_station_mm'],(int,float)) and Decimal(str(row['proposed_station_mm']))==value
            assert row['basis']=='LOCAL_ORIGIN' and row['basis_point_id']==a['id']
            assert row['basis_id']==stored[a['id']]['basis_id'] and row['basis_id']
            assert row['stored_proof_state'].startswith('CURRENT')
        assert all(r['existing_station_mm'] is None for r in station_rows if r['point_id'] not in ids)
        constraints=records('Station constraints');saved_delta=next(r for r in constraints if r['kind']=='DELTA')
        assert saved_delta['source_text']==source_text and saved_delta['source_format']==source_format
        assert isinstance(saved_delta['value_mm'],(int,float)) and Decimal(str(saved_delta['value_mm']))==Decimal(expected)
        assert saved_delta['source_proposal_id']==proposal['id'] and saved_delta['source_sha256']==SHA
        source_lengths=records('Source lengths')
        assert len(source_lengths)==4
        assert all(isinstance(r['proposed_distance_mm'],(int,float)) and r['station_mm'] is None for r in source_lengths)
        assert sorted(Decimal(str(r['proposed_distance_mm'])) for r in source_lengths)==[Decimal('12.7'),Decimal('50.8'),Decimal('53.975'),Decimal('69.85')]
        assert all('UNSIGNED' in r['direction_state'] and r['source_sha256']==SHA for r in source_lengths)
        printed=records('Printed coordinates');assert len(printed)==12
        assert all(isinstance(r['proposed_value_mm'],(int,float)) and r['accepted_value_mm'] is None for r in printed)
        assert all(r['proposed_value_mm']<0 for r in printed if r['axis']=='Y')
        supports=records('Supports')
        assert sorted(Decimal(str(r['station'])) for r in supports if r['station'] is not None)==[Decimal(0),Decimal(expected)]
        assert [Decimal(str(r['gap'])) for r in supports if r['gap'] is not None]==[Decimal(expected)]
        elements=records('CAESAR input');assert len(elements)==1
        assert Decimal(str(elements[0]['route_distance']))==Decimal(expected)
        assert all(elements[0][axis] is None for axis in ('dx','dy','dz'))
        book.close()
        source=context.request.get(project+'/sources/'+sheet['source_id'])
        assert source.ok and hashlib.sha256(source.body()).hexdigest()==SHA
        page.screenshot(path='/tmp/caesar-screens/real-1010-stations-'+case+'.png',full_page=True)
        if index==len(CASES)-1:
            # Withdrawal exercises the UI's separate reason/confirmation flow.
            # Prior values are retained as stale history, never silently moved
            # or reused for a support gap after their source is removed.
            dialog=open_stations()
            dialog.get_by_label('Saved station constraint',exact=True).select_option(delta['id'])
            dialog.get_by_role('button',name='Remove station evidence',exact=True).click()
            dialog=page.get_by_role('dialog',name='Remove station evidence',exact=True)
            dialog.get_by_label('Station decision evidence',exact=True).fill('SOFTWARE VALIDATION ONLY: withdraw this test constraint to verify stale station proof and support-gap suppression; the actual printed source remains unchanged.')
            dialog.get_by_label('Confirm station solution decision',exact=True).check()
            dialog.get_by_role('button',name='Remove selected station evidence',exact=True).click()
            expect(dialog).to_have_count(0)
            withdrawn=context.request.get(project).json();later=next(n for n in withdrawn['nodes'] if n['id']==b['id'])
            assert 'STATION_SOLUTION_STALE' in later['station_review_reasons'] and later['support_gap_mm'] is None
            assert all(c['id']!=delta['id'] for c in context.request.get(project+'/physical-model/stations').json()['constraints'])
        print('PASS: real '+source_text+' witness, route-required and relative-only gates, explicit localdatum, exact '+expected+'mm station chain, retained unknown XYZ/other stations and sixinchflag.',flush=True)
