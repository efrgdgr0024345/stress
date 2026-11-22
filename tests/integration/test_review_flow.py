"""Human review boundaries, factor replay protection and immutable issues.

All accounts, passwords, authenticator seeds and files are disposable fixtures.
These tests never sign or approve a real engineering project.
"""
from copy import deepcopy
import hashlib
import io
import json
import time
import unittest
import zipfile
from fastapi.testclient import TestClient
from packages.reviews import scopes
from services.api import main, account_security as security
from services.api.updates import read, write
from tests.integration import test_api as fixtures


class ReviewFlowTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    pdf=fixtures.ApiTests.pdf
    upload=fixtures.ApiTests.upload
    node=fixtures.ApiTests.node
    password='Disposable-fixture-password-2026'

    def account(self,role='engineer',suffix='one'):
        email=f'{role}-{suffix}@example.test'
        response=self.client.post('/api/v1/system/people',json={
            'name':role+' '+suffix,'email':email,'role':role,'password':self.password})
        self.assertEqual(response.status_code,201,response.text)
        client=TestClient(main.app)
        login=client.post('/api/v1/auth/login',json={'email':email,'password':self.password})
        self.assertEqual(login.status_code,200,login.text)
        return client,response.json()

    def enroll(self,client):
        result=client.post('/api/v1/account/security/enroll',json={'password':self.password})
        self.assertEqual(result.status_code,200,result.text)
        seed=result.json()['secret']
        code=security.totp(seed,int(time.time()/30))
        confirmed=client.post('/api/v1/account/security/confirm',json={'code':code})
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        return seed,confirmed.json()['recovery_codes']

    def reviewable(self):
        # The engineer owns all edits; the hosting administrator is independent.
        engineer,actor=self.account()
        response=engineer.post('/api/v1/projects',json={'title':'Disposable review fixture','line_id':'REVIEW-001'})
        p=response.json()
        response=engineer.post(f"/api/v1/projects/{p['id']}/sources?version={p['version']}",files={'file':('synthetic.pdf',self.pdf(),'application/pdf')})
        self.assertEqual(response.status_code,200,response.text)
        return engineer,actor,response.json()

    def sign_all(self,client,p):
        path=f"/api/v1/projects/{p['id']}/reviews"
        keys=[s['key'] for s in client.get(path).json()['scopes']]
        for key in keys:
            data=client.get(path).json()
            scope=next(s for s in data['scopes'] if s['key']==key)
            response=client.post(path+'/sign',json={'version':data['revision'],'scope':key,
                'reason':'Inspected synthetic source; unresolved evidence is explicitly retained.',
                'acknowledge':scope['blocking'],'confirmed':True})
            self.assertEqual(response.status_code,200,response.text)
            p=response.json()['project']
        return p

    def final_body(self,p,client=None):
        data=(client or self.client).get(f"/api/v1/projects/{p['id']}/reviews").json()
        return {'version':p['version'],'reason':'Independently checked this disposable engineering-review fixture.',
                'level':'ENGINEERING_REVIEW','confirmed':True,'acknowledge':[v['id'] for v in data['issues']]}

    def test_rfc6238_vector_and_factor_enrollment_recovery_replay(self):
        import base64
        seed=base64.b32encode(b'12345678901234567890').decode()
        self.assertEqual(security.totp(seed,59//30,digits=8),'94287082')
        client,actor=self.account()
        secret,codes=self.enroll(client)
        self.assertEqual(len(codes),10)
        stored=security.path(main,actor['id'])
        self.assertEqual(stored.stat().st_mode&0o777,0o600)
        self.assertNotIn(codes[0].replace('-',''),stored.read_text())
        self.assertNotIn(secret,str(client.get('/api/v1/account/security').json()))
        login={'email':actor['email'],'password':self.password}
        self.assertEqual(client.post('/api/v1/auth/login',json=login).status_code,401)
        # Enrollment's counter has been consumed and cannot immediately log in.
        login['code']=security.totp(secret,read(stored)['last_counter'])
        self.assertEqual(client.post('/api/v1/auth/login',json=login).status_code,401)
        login['code']=codes[0]
        self.assertEqual(client.post('/api/v1/auth/login',json=login).status_code,200)
        self.assertEqual(client.post('/api/v1/auth/login',json=login).status_code,401)
        self.assertEqual(client.get('/api/v1/account/security').json()['recovery_codes_remaining'],9)
        # A future counter is valid within the accepted clock skew, once.
        login['code']=security.totp(secret,int(time.time()/30)+1)
        self.assertEqual(client.post('/api/v1/auth/login',json=login).status_code,200)
        self.assertEqual(client.post('/api/v1/auth/login',json=login).status_code,429)

    def test_enrollment_bound_to_session_expiry_and_password(self):
        client,actor=self.account()
        denied=client.post('/api/v1/account/security/enroll',json={'password':'wrong'})
        self.assertEqual(denied.status_code,401)
        seed=client.post('/api/v1/account/security/enroll',json={'password':self.password}).json()['secret']
        another=TestClient(main.app)
        another.post('/api/v1/auth/login',json={'email':actor['email'],'password':self.password})
        code=security.totp(seed,int(time.time()/30))
        self.assertEqual(another.post('/api/v1/account/security/confirm',json={'code':code}).status_code,401)
        filename=security.path(main,actor['id']);value=read(filename)
        value['pending']['expires']=time.time()-1;write(filename,value)
        self.assertEqual(client.post('/api/v1/account/security/confirm',json={'code':code}).status_code,401)
        self.assertFalse(client.get('/api/v1/account/security').json()['enabled'])

    def test_missing_or_replaced_factor_storage_cannot_allow_password_only_login(self):
        client,actor=self.account();self.enroll(client)
        filename=security.path(main,actor['id']);original=filename.read_bytes()
        filename.unlink()
        login={'email':actor['email'],'password':self.password}
        self.assertEqual(client.post('/api/v1/auth/login',json=login).status_code,503)
        self.assertEqual(client.get('/api/v1/account/security').status_code,503)
        write(filename,{'enabled':False})
        self.assertEqual(client.post('/api/v1/auth/login',json=login).status_code,503)
        filename.write_bytes(original)
        self.assertEqual(client.post('/api/v1/auth/login',json=login).status_code,401)

    def test_role_changes_revoke_sessions_and_reviewers_cannot_edit(self):
        engineer,actor=self.account()
        p=self.create()
        result=self.client.patch('/api/v1/system/people/'+actor['id'],json={
            'role':'reviewer','enabled':True,'reason':'Independent reviewer for synthetic fixture'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(engineer.get('/api/v1/projects').status_code,401)
        engineer.post('/api/v1/auth/login',json={'email':actor['email'],'password':self.password})
        self.assertEqual(engineer.post('/api/v1/projects',json={'title':'Cannot edit','line_id':'X'}).status_code,403)
        self.assertEqual(engineer.post(f"/api/v1/projects/{p['id']}/sources?version=1",files={'file':('bad.pdf',b'not parsed')}).status_code,403)
        self.assertEqual(engineer.get('/api/v1/system/people').status_code,403)
        self.client.patch('/api/v1/system/people/'+actor['id'],json={
            'role':'reviewer','enabled':False,'reason':'Synthetic fixture account disabled'})
        self.assertEqual(engineer.post('/api/v1/auth/login',json={'email':actor['email'],'password':self.password}).status_code,401)
        self.assertEqual(self.client.patch('/api/v1/system/people/local-engineer',json={
            'role':'viewer','enabled':False,'reason':'Cannot disable hosting operator'}).status_code,409)

    def test_validation_errors_do_not_reflect_passwords_or_factor_secrets(self):
        sentinel='SENSITIVE_SENTINEL'*100
        response=self.client.post('/api/v1/system/people',json={
            'name':'Fixture','email':'invalid','password':sentinel,'role':'unexpected'})
        self.assertEqual(response.status_code,422)
        self.assertNotIn(sentinel,response.text)
        response=self.client.post('/api/v1/auth/login',json={'email':'x','password':sentinel,'code':sentinel})
        self.assertEqual(response.status_code,422)
        self.assertNotIn(sentinel,response.text)
        for filename in main.DATA.rglob('*.log'):
            self.assertNotIn(sentinel,filename.read_text(errors='replace'))

    def test_explicit_scoped_review_idempotence_and_layout_does_not_change_geometry(self):
        engineer,actor,p=self.reviewable()
        response=engineer.post(f"/api/v1/projects/{p['id']}/nodes",json=self.node(p,'100 mm','Synthetic explicit dimension evidence'))
        self.assertEqual(response.status_code,200,response.text);p=response.json()
        p=self.sign_all(engineer,p)
        before=engineer.get(f"/api/v1/projects/{p['id']}/reviews").json()
        self.assertTrue(all(s['review'] for s in before['scopes']))
        material=next(s for s in before['scopes'] if s['kind']=='materials')
        body={'version':p['version'],'scope':material['key'],'reason':'Same accepted synthetic material review',
              'acknowledge':material['blocking'],'confirmed':True}
        again=engineer.post(f"/api/v1/projects/{p['id']}/reviews/sign",json=body)
        self.assertEqual(again.status_code,200,again.text)
        self.assertEqual(again.json()['project']['version'],p['version'])
        n=p['nodes'][0]
        body=self.node(p,'100 mm','Synthetic explicit dimension evidence')
        body['instances'][0]['bubble']=[190,130]
        response=engineer.patch(f"/api/v1/projects/{p['id']}/nodes/{n['id']}",json=body)
        self.assertEqual(response.status_code,200,response.text)
        after=engineer.get(f"/api/v1/projects/{p['id']}/reviews").json()
        geometry=lambda data:next(s for s in data['scopes'] if s['kind']=='geometry')
        self.assertEqual(geometry(before)['sha256'],geometry(after)['sha256'])
        self.assertIsNotNone(geometry(after)['review'])
        self.assertEqual(next(s for s in after['scopes'] if s['kind']=='layout')['state'],'STALE')
        # Changing the physical evidence invalidates the geometry signature.
        body['version']=response.json()['version'];body['dimension']='101 mm'
        engineer.patch(f"/api/v1/projects/{p['id']}/nodes/{n['id']}",json=body)
        final=engineer.get(f"/api/v1/projects/{p['id']}/reviews").json()
        self.assertEqual(geometry(final)['state'],'STALE')

    def test_partial_processing_reviews_are_ready_only_after_page_evidence(self):
        engineer,actor,p=self.reviewable()
        sheet=p['sheets'][0]
        # A real pipeline run is not needed to demonstrate the pure scope contract.
        waiting=scopes(p,{sheet['source_id']})
        self.assertFalse(next(s for s in waiting if s['kind']=='materials')['ready'])
        p['automation']={'partial_pages':{sheet['id']:{'source_sha256':sheet['sha256']}}}
        ready=scopes(p,{sheet['source_id']})
        self.assertTrue(all(s['ready'] for s in ready))
        p['automation']['partial_pages'][sheet['id']]['source_sha256']='different-source'
        self.assertFalse(next(s for s in scopes(p,{sheet['source_id']}) if s['kind']=='layout')['ready'])

    def test_independent_approval_requires_mfa_all_signoffs_and_explicit_issues(self):
        engineer,actor,p=self.reviewable()
        path=f"/api/v1/projects/{p['id']}/reviews"
        self.assertEqual(self.client.post(path+'/approve',json=self.final_body(p)).status_code,409)
        self.enroll(self.client)
        response=self.client.post(path+'/approve',json=self.final_body(p))
        self.assertEqual(response.status_code,409)
        self.assertIn('Every current project section',response.text)
        p=self.sign_all(engineer,p)
        # Role prevents a preparing engineer from elevating themselves to lead.
        self.assertEqual(engineer.post(path+'/approve',json=self.final_body(p,engineer)).status_code,403)
        body=self.final_body(p);body['acknowledge']=[]
        self.assertEqual(self.client.post(path+'/approve',json=body).status_code,409)
        approved=self.client.post(path+'/approve',json=self.final_body(p))
        self.assertEqual(approved.status_code,200,approved.text)
        receipt=approved.json()['approval']
        self.assertEqual(receipt['level'],'ENGINEERING_REVIEW')
        self.assertEqual(receipt['actor_id'],'local-engineer')
        self.assertTrue(receipt['outstanding_issues'])
        history=self.client.get(path).json()['approvals']
        self.assertEqual(history[0]['id'],receipt['id'])
        self.assertNotIn('snapshot',history[0])
        repeat=self.client.post(path+'/approve',json=self.final_body(p))
        self.assertEqual(repeat.status_code,200,repeat.text)
        self.assertEqual(repeat.json()['approval']['id'],receipt['id'])

    def test_approved_packet_immutable_across_edits_and_detects_tampering(self):
        engineer,actor,p=self.reviewable();p=self.sign_all(engineer,p);self.enroll(self.client)
        path=f"/api/v1/projects/{p['id']}/reviews"
        response=self.client.post(path+'/approve',json=self.final_body(p))
        self.assertEqual(response.status_code,200,response.text)
        receipt=response.json()['approval'];download=path+'/approvals/'+receipt['id']
        original=self.client.get(download+'/download').content
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            self.assertEqual(json.loads(archive.read('approval-receipt.json'))['signature'],receipt['signature'])
            self.assertEqual(json.loads(archive.read('approved-project-snapshot.json'))['version'],p['version'])
            signatures=json.loads(archive.read('section-signoffs.json'))
            self.assertEqual({s['id'] for s in signatures},set(receipt['engineer_signoffs']))
        verify=self.client.get(download+'/verify')
        self.assertEqual(verify.status_code,200,verify.text)
        self.assertEqual(verify.json()['packet_sha256'],hashlib.sha256(original).hexdigest())
        edited=engineer.patch(f"/api/v1/projects/{p['id']}/sheets/{p['sheets'][0]['id']}",json={
            'version':p['version'],'printed_id':'REVISED-TEST','line_id':p['line_id'],'axis':[220,210]})
        self.assertEqual(edited.status_code,200,edited.text)
        self.assertEqual(edited.json()['status'],'DRAFT')
        self.assertNotIn('review_approval',edited.json())
        self.assertEqual(self.client.get(download+'/download').content,original)
        target=main.DATA/'approvals'/f"{receipt['id']}.zip"
        target.write_bytes(original+b'TAMPERED')
        self.assertEqual(self.client.get(download+'/download').status_code,409)
        self.assertEqual(self.client.get(download+'/verify').status_code,409)

    def test_scope_acknowledgments_are_required_and_tenant_access_is_hidden(self):
        engineer,actor,p=self.reviewable()
        path=f"/api/v1/projects/{p['id']}/reviews"
        data=engineer.get(path).json();scope=next(s for s in data['scopes'] if s['kind']=='materials')
        response=engineer.post(path+'/sign',json={'version':p['version'],'scope':scope['key'],
            'reason':'Review with no acknowledgment should fail','confirmed':True})
        self.assertEqual(response.status_code,409,response.text)
        with main.db() as conn:conn.execute('UPDATE projects SET tenant=? WHERE id=?',('another-tenant',p['id']))
        self.assertEqual(engineer.get(path).status_code,404)
        self.assertEqual(engineer.get(path+'/approvals/'+main.uid()+'/download').status_code,404)

    def test_processing_blocks_final_issue_but_ready_sections_remain_reviewable(self):
        engineer,actor,p=self.reviewable();sheet=p['sheets'][0]
        path=f"/api/v1/projects/{p['id']}/reviews"
        run=main.uid()
        with main.db() as conn:
            conn.execute('INSERT INTO pipeline_runs(id,project_id,source_id,state,progress) VALUES (?,?,?,?,?)',(run,p['id'],sheet['source_id'],'QUEUED','{}'))
        state=engineer.get(path).json();material=next(s for s in state['scopes'] if s['kind']=='materials')
        self.assertFalse(material['ready'])
        response=engineer.post(path+'/sign',json={'version':p['version'],'scope':material['key'],
            'reason':'Cannot sign an unprocessed synthetic page','acknowledge':material['blocking'],'confirmed':True})
        self.assertEqual(response.status_code,409)
        p['automation']={'partial_pages':{sheet['id']:{'source_sha256':sheet['sha256']}}}
        with main.db() as conn:conn.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p),p['id']))
        p=self.sign_all(engineer,p)
        self.assertTrue(engineer.get(path).json()['processing'])
        self.enroll(self.client)
        response=self.client.post(path+'/approve',json=self.final_body(p))
        self.assertEqual(response.status_code,409,response.text)
        self.assertIn('still running',response.text)
        with main.db() as conn:conn.execute("UPDATE pipeline_runs SET state='DONE' WHERE id=?",(run,))
        with main.db() as conn:conn.execute('INSERT INTO pipeline_outbox VALUES (?,?,?,?)',(p['id'],p['version'],actor['id'],time.time()))
        self.assertEqual(self.client.post(path+'/approve',json=self.final_body(p)).status_code,409)

    def test_signature_tampering_and_unknown_engineering_block_verified_release(self):
        engineer,actor,p=self.reviewable();p=self.sign_all(engineer,p);self.enroll(self.client)
        path=f"/api/v1/projects/{p['id']}/reviews"
        body=self.final_body(p);body['level']='VERIFIED_FOR_MODELLING'
        result=self.client.post(path+'/approve',json=body)
        self.assertEqual(result.status_code,409,result.text)
        self.assertIn('Critical source/model limitations',result.text)
        with main.db() as conn:
            row=conn.execute('SELECT id,data FROM review_signoffs WHERE project_id=? LIMIT 1',(p['id'],)).fetchone()
            value=json.loads(row['data']);value['reason']='Tampered decision'
            conn.execute('UPDATE review_signoffs SET data=? WHERE id=?',(json.dumps(value),row['id']))
        self.assertEqual(self.client.get(path).status_code,409)

    def test_valid_old_seal_cannot_be_reindexed_as_a_new_content_review(self):
        engineer,actor,p=self.reviewable();p=self.sign_all(engineer,p)
        path=f"/api/v1/projects/{p['id']}/reviews"
        response=engineer.post(f"/api/v1/projects/{p['id']}/nodes",json=self.node(p,'100 mm','New explicit synthetic dimension evidence'))
        self.assertEqual(response.status_code,200,response.text)
        scope=next(s for s in engineer.get(path).json()['scopes'] if s['kind']=='geometry')
        self.assertEqual(scope['state'],'STALE')
        # Corrupt only the unsigned index. The old signed payload still verifies
        # on its own, but it must never attest to the new geometry's content.
        with main.db() as conn:conn.execute('UPDATE review_signoffs SET content_sha=? WHERE project_id=? AND scope=?',(scope['sha256'],p['id'],scope['key']))
        self.assertEqual(engineer.get(path).status_code,409)

    def test_same_preparer_cannot_approve_and_factor_assurance_expires(self):
        p=self.upload(self.create());p=self.sign_all(self.client,p)
        secret,codes=self.enroll(self.client)
        path=f"/api/v1/projects/{p['id']}/reviews"
        body=self.final_body(p)
        response=self.client.post(path+'/approve',json=body)
        self.assertEqual(response.status_code,409,response.text)
        self.assertIn('independent reviewer',response.text)
        with main.db() as conn:conn.execute('UPDATE session_assurance SET mfa_at=0')
        self.assertEqual(self.client.post(path+'/approve',json=body).status_code,401)
        body['code']=codes[0]
        response=self.client.post(path+'/approve',json=body)
        self.assertEqual(response.status_code,409,response.text)
        self.assertIn('independent reviewer',response.text)
