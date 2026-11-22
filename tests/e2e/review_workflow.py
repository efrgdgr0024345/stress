"""Two disposable people review a synthetic source; no real sign-offs."""
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile
import fitz
from playwright.sync_api import expect
from services.api.account_security import totp


def exercise_reviews(page,context,base,browser):
    page.get_by_role('button',name='Account security',exact=True).click()
    dialog=page.get_by_role('dialog',name='Account security',exact=True)
    dialog.get_by_role('button',name='Set up authenticator',exact=True).click()
    expect(dialog.locator('.setup-key')).to_be_visible()
    secret=dialog.locator('.setup-key').inner_text()
    expect(dialog.get_by_alt_text('Authenticator setup QR code')).to_be_visible()
    assert dialog.get_by_alt_text('Authenticator setup QR code').get_attribute('src').startswith('data:image/png;')
    dialog.get_by_label('Six-digit authenticator code').fill(totp(secret,int(time.time()/30)))
    dialog.get_by_role('button',name='Confirm authenticator',exact=True).click()
    expect(dialog.get_by_role('heading',name='Keep your recovery codes')).to_be_visible()
    with page.expect_download() as recovery_download:
        dialog.get_by_role('button',name='Save recovery codes',exact=True).click()
    recovery_text=Path(recovery_download.value.path()).read_text()
    assert len(dialog.locator('.recovery-codes code').all())==10
    assert dialog.locator('.recovery-codes code').first.inner_text() in recovery_text
    assert secret not in recovery_text
    dialog.get_by_role('button',name='Close dialog',exact=True).click()
    page.get_by_role('button',name='People & access',exact=True).click()
    expect(page.get_by_role('heading',name='People.')).to_be_visible()
    page.get_by_role('button',name='Add account',exact=True).click()
    dialog=page.get_by_role('dialog',name='Add workspace account')
    dialog.get_by_label('Name',exact=True).fill('Disposable review engineer')
    dialog.get_by_label('Email',exact=True).fill('disposable-review-engineer@example.test')
    dialog.get_by_label('Password',exact=True).fill('Disposable-browser-fixture-2026')
    dialog.get_by_label('Role',exact=True).select_option('engineer')
    dialog.get_by_role('button',name='Create account',exact=True).click()
    expect(dialog).to_have_count(0)
    expect(page.locator('.people-table')).to_contain_text('Disposable review engineer')
    engineer=browser.new_context(accept_downloads=True,viewport={'width':1440,'height':1000})
    try:
        response=engineer.request.post(base+'/api/v1/auth/login',data={'email':'disposable-review-engineer@example.test','password':'Disposable-browser-fixture-2026'})
        assert response.ok,response.status
        p=engineer.request.post(base+'/api/v1/projects',data={'title':'Disposable two-person review','line_id':'SYNTHETIC-REVIEW-001'}).json()
        with fitz.open() as document:
            source=document.new_page(width=600,height=500)
            source.insert_text((60,100),'SYNTHETIC SOFTWARE FIXTURE ONLY - NOT ENGINEERING DATA')
            source.insert_text((60,140),'Unresolved facts remain explicitly reported in the sealed review issue.')
            raw=document.tobytes()
        response=engineer.request.post(base+f"/api/v1/projects/{p['id']}/sources?version=1",multipart={'file':{'name':'synthetic-review.pdf','mimeType':'application/pdf','buffer':raw}})
        assert response.ok,response.text()
        project_id=p['id']
        ep=engineer.new_page()
        ep.goto(base+f'/?project={project_id}&view=validation',wait_until='domcontentloaded')
        expect(ep.get_by_role('heading',name='Evidence before release.')).to_be_visible()
        panel=ep.get_by_role('region',name='Project review and sign-off')
        # Four logical review groups share the unchanged project workspace.
        expect(panel.get_by_role('progressbar',name='Sections reviewed')).to_have_attribute('aria-valuemax','4')
        for count in range(4):
            panel.get_by_role('button',name='Review section',exact=True).first.click()
            dialog=ep.get_by_role('dialog')
            dialog.get_by_label('Review evidence and decision',exact=True).fill('Inspected synthetic software fixture; every listed source limitation is deliberately retained.')
            for checkbox in dialog.get_by_role('checkbox').all():checkbox.check()
            dialog.get_by_role('button',name='Sign section review',exact=True).click()
            expect(dialog).to_have_count(0)
            expect(panel.get_by_role('progressbar',name='Sections reviewed')).to_have_attribute('aria-valuenow',str(count+1))
        expect(panel.get_by_role('button',name='Approve engineering-review issue')).to_be_disabled()
        page.goto(base+f'/?project={project_id}&view=validation',wait_until='domcontentloaded')
        panel=page.get_by_role('region',name='Project review and sign-off')
        expect(panel.get_by_role('button',name='Approve engineering-review issue')).to_be_enabled()
        panel.get_by_role('button',name='Approve engineering-review issue').click()
        dialog=page.get_by_role('dialog',name='Approve engineering-review issue',exact=True)
        dialog.get_by_label('Review evidence and decision',exact=True).fill('Independently inspected the synthetic review. All unresolved engineering facts remain listed and unapproved for modelling.')
        for checkbox in dialog.get_by_role('checkbox').all():checkbox.check()
        dialog.get_by_role('button',name='Seal review issue',exact=True).click()
        expect(dialog).to_have_count(0)
        expect(panel.get_by_role('heading',name='Preserved approved issues')).to_be_visible()
        with page.expect_download() as packet_download:panel.get_by_role('link',name='Download',exact=True).click()
        packet=Path(packet_download.value.path()).read_bytes()
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            receipt=json.loads(archive.read('approval-receipt.json'))
            frozen=json.loads(archive.read('approved-project-snapshot.json'))
        assert receipt['level']=='ENGINEERING_REVIEW' and receipt['outstanding_issues']
        assert frozen['review_approval']['id']==receipt['id']
        verify=context.request.get(base+f"/api/v1/projects/{project_id}/reviews/approvals/{receipt['id']}/verify")
        assert verify.ok and verify.json()['packet_sha256']==hashlib.sha256(packet).hexdigest()
        page.screenshot(path='/tmp/caesar-screens/review-signoff.png',full_page=True)
        # A new draft must not replace the preserved issue or its signature.
        current=engineer.request.get(base+f'/api/v1/projects/{project_id}').json()
        changed=engineer.request.patch(base+f"/api/v1/projects/{project_id}/sheets/{current['sheets'][0]['id']}",data={'version':current['version'],'printed_id':'REVISED-SYNTHETIC','line_id':current['line_id'],'axis':[200,200]})
        assert changed.ok,changed.text()
        assert changed.json()['status']=='DRAFT' and 'review_approval' not in changed.json()
        repeated=context.request.get(base+f"/api/v1/projects/{project_id}/reviews/approvals/{receipt['id']}/download")
        assert repeated.body()==packet
    finally:engineer.close()
    page.goto(base+'/',wait_until='domcontentloaded')
    expect(page.get_by_role('heading',name='Projects.')).to_be_visible()
    print('PASS: local QR/recovery codes, people accounts, scoped human decisions, independent MFA approval, sealed issue integrity and new-draft preservation.',flush=True)
