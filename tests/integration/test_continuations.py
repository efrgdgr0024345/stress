from copy import deepcopy
import io
import unittest
import zipfile
import fitz
from openpyxl import load_workbook
from fastapi.testclient import TestClient
from services.api import main
from services.api.updates import required_security_contract
from packages.pdf import content_hash
from tests.integration import test_api as fixtures


class ContinuationApiTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload
    node=fixtures.ApiTests.node

    def model(self,offset='0',verified=True):
        with fitz.open() as doc:
            for i in range(2):doc.new_page(width=600,height=500).insert_text((50,50),f'SYNTHETIC ONLY SHEET {i+1} OF 2 CONT. '+('ON SHEET 2' if i==0 else 'FROM SHEET 1'))
            raw=doc.tobytes()
        p=self.upload(self.create(),raw)
        for i,sheet in enumerate(p['sheets']):
            response=self.client.patch(f"/api/v1/projects/{p['id']}/sheets/{sheet['id']}",json={'version':p['version'],
                'printed_id':f'SHEET {i+1} OF 2','line_id':p['line_id'],'axis':None,'table':None,'confirm_identity':verified})
            self.assertEqual(response.status_code,200,response.text);p=response.json()
        for order in range(2):
            body=self.node(p,'100 mm','SYNTHETIC independent source continuation station')
            body.update(kind='continuation',order=order)
            body['instances'][0]['sheet_id']=p['sheets'][order]['id']
            response=self.client.post(f"/api/v1/projects/{p['id']}/nodes",json=body)
            self.assertEqual(response.status_code,200,response.text);p=response.json()
        from decimal import Decimal
        for index,n in enumerate(p['nodes']):
            for axis,value in [('X','E '+str(1000+(Decimal(offset) if index else 0))+' mm'),('Y','S 500 mm'),('Z','EL 300 mm')]:
                body={'version':p['version'],'kind':'COORDINATE','axis':axis,'from_point_id':n['id'],
                      'to_point_id':None,'source_text':value,'tolerance_text':'0 mm',
                      'sheet_id':p['sheets'][index]['id'],'evidence':'SYNTHETIC printed independent engineering coordinate','confirmed':True}
                response=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/dimensions",json=body)
                self.assertEqual(response.status_code,200,response.text);p=response.json()
        return p

    def match(self,p,decision='PROPOSE',**changes):
        body={'version':p['version'],'left_point_id':p['nodes'][0]['id'],'right_point_id':p['nodes'][1]['id'],
              'left_size':'8 in','right_size':'8','decision':decision,'topology_confirmed':True,
              'evidence':'SYNTHETIC inspected same full-line interface and reciprocal source topology','confirmed':True}
        body.update(changes)
        return self.client.post(f"/api/v1/projects/{p['id']}/continuations",json=body)

    def test_exact_source_proof_unifies_identity_and_preserves_native_instances(self):
        p=self.model();left,right=[n['id'] for n in p['nodes']]
        response=self.match(p,'ACCEPT_IDENTITY');self.assertEqual(response.status_code,200,response.text);p=response.json()
        self.assertEqual(len(p['nodes']),1);n=p['nodes'][0]
        self.assertEqual(n['id'],left);self.assertEqual(p['point_aliases'][right],left)
        self.assertEqual(len(n['instances']),2);self.assertEqual(n['station_mm'],'100')
        self.assertEqual(len(p['physical_model']['constraints']),6)
        self.assertEqual({c['from_point_id'] for c in p['physical_model']['constraints']},{left})
        self.assertTrue(all(c['source_text'] for c in p['physical_model']['constraints']))
        self.assertEqual(p['continuations'][-1]['status'],'ACCEPTED')
        self.assertFalse(n.get('continuation_review_reasons'))
        self.assertEqual(required_security_contract(main.DATA),3)
        data=self.client.get(f"/api/v1/projects/{p['id']}/results").json()
        table=next(t for t in data['tables'] if t['name']=='Continuations')
        self.assertEqual(len(table['rows']),3)
        self.assertTrue(all(r['left']==r['right']==r['shared']==n['number'] for r in table['rows']))
        xlsx=self.client.get(f"/api/v1/projects/{p['id']}/results/workbook")
        book=load_workbook(io.BytesIO(xlsx.content),read_only=True,data_only=True)
        self.assertEqual(book['Continuations']['H6'].value,0);book.close()
        result=self.client.post(f"/api/v1/projects/{p['id']}/exports",json={'version':p['version']})
        self.assertEqual(result.status_code,200,result.text)
        bundle=self.client.get(f"/api/v1/projects/{p['id']}/artifacts/{result.json()['id']}/download")
        source=self.client.get(f"/api/v1/projects/{p['id']}/sources/{p['sheets'][0]['source_id']}")
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as z,fitz.open(stream=source.content,filetype='pdf') as before,fitz.open(stream=z.read('annotated-review.pdf'),filetype='pdf') as after:
            for i in range(2):
                self.assertEqual(content_hash(before[i]),content_hash(after[i]))
                numbers=[a for a in after[i].annots() if a.info.get('subject','').startswith('number |')]
                self.assertEqual(len(numbers),1);self.assertEqual(numbers[0].info['content'],str(n['number']))

    def test_one_inch_discrepancy_keeps_both_points_and_blue_reasons(self):
        p=self.model('25.4');before=deepcopy(p)
        response=self.match(p);self.assertEqual(response.status_code,200,response.text);p=response.json()
        self.assertEqual(len(p['nodes']),2)
        self.assertEqual(p['physical_model']['constraints'],before['physical_model']['constraints'])
        self.assertEqual(p['continuations'][-1]['delta_mm'],{'X':'25.4','Y':'0','Z':'0'})
        self.assertTrue(all('MATCH_TO_BE_CONFIRMED_BY_ENGINEER' in n['reasons'] for n in p['nodes']))
        self.assertEqual(self.match(p,'ACCEPT_IDENTITY').status_code,409)
        response=self.match(p,'REJECT');self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(all('MATCH_TO_BE_CONFIRMED_BY_ENGINEER' not in n['reasons'] for n in response.json()['nodes']))

    def test_identity_requires_topology_and_confirmed_sheet_register(self):
        p=self.model()
        self.assertEqual(self.match(p,'ACCEPT_IDENTITY',topology_confirmed=False).status_code,422)
        self.assertEqual(self.match(p,'ACCEPT_IDENTITY',right_size='2').status_code,409)
        stale=self.match(p,version=p['version']-1);self.assertEqual(stale.status_code,409)
        p=self.model(verified=False)
        self.assertEqual(self.match(p,'ACCEPT_IDENTITY').status_code,409)

    def test_changed_anchor_or_coordinate_evidence_invalidates_accepted_identity(self):
        p=self.match(self.model(),'ACCEPT_IDENTITY').json();n=p['nodes'][0]
        body=self.node(p,'100 mm',n['evidence']);body.update(kind=n['kind'],order=n['order'],instances=deepcopy(n['instances']))
        body['instances'][1]['anchor']=[170,220]
        response=self.client.patch(f"/api/v1/projects/{p['id']}/nodes/{n['id']}",json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('CONTINUATION_SOURCE_STALE',response.json()['nodes'][0]['reasons'])
        p=response.json();link=p['continuations'][-1]
        response=self.client.patch(f"/api/v1/projects/{p['id']}/continuations/{link['id']}",json={'version':p['version'],
            'decision':'REVALIDATE','topology_confirmed':True,'evidence':'SYNTHETIC reinspected moved source anchor against both independent coordinate sets','confirmed':True})
        self.assertEqual(response.status_code,200,response.text);p=response.json()
        self.assertFalse(p['nodes'][0].get('continuation_review_reasons'))
        response=self.client.patch(f"/api/v1/projects/{p['id']}/continuations/{link['id']}",json={'version':p['version'],
            'decision':'WITHDRAW','evidence':'SYNTHETIC reviewer withdraws interface acceptance pending source inspection','confirmed':True})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('WITHDRAWN',response.json()['nodes'][0]['reasons']);self.assertEqual(len(response.json()['nodes']),1)

    def test_unresolved_source_label_requires_explicit_same_sheet_association(self):
        from packages.engineering.continuations import source_candidates
        from packages.automation.extract import extract_page
        p=self.model()
        source=main.DATA/'sources'/f"{p['sheets'][0]['source_id']}.pdf"
        candidates=[]
        for s in p['sheets']:candidates.extend(source_candidates(extract_page(source,s['page_index'],ocr=False),s))
        self.assertEqual(len(candidates),2)
        p['automation']={'continuation_candidates':candidates}
        import json
        with main.db() as conn:conn.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p),p['id']))
        report=self.client.get(f"/api/v1/projects/{p['id']}/continuations").json()
        self.assertEqual(sum(i['code']=='UNRESOLVED_CONTINUATION_REFERENCE' for i in report['issues']),2)
        self.assertEqual(self.match(p,'ACCEPT_IDENTITY',left_candidate_id=candidates[1]['id']).status_code,422)
        response=self.match(p,'ACCEPT_IDENTITY',left_candidate_id=candidates[0]['id'],right_candidate_id=candidates[1]['id'])
        self.assertEqual(response.status_code,200,response.text)
        report=self.client.get(f"/api/v1/projects/{p['id']}/continuations").json()
        self.assertEqual(report['issues'],[])

    def test_source_direction_axis_validation_and_editor_authorization(self):
        p=self.model();c=p['physical_model']['constraints'][1]
        self.assertEqual(c['source_direction'],'S');self.assertEqual(c['value_mm'],'-500')
        body={k:c[k] for k in ('kind','axis','from_point_id','to_point_id','source_text','tolerance_text','sheet_id','evidence')}
        body.update(version=p['version'],source_text='E 500 mm',axis='Y',confirmed=True)
        self.assertEqual(self.client.post(f"/api/v1/projects/{p['id']}/physical-model/dimensions",json=body).status_code,422)
        self.assertEqual(TestClient(main.app).get(f"/api/v1/projects/{p['id']}/continuations").status_code,401)
        with main.db() as conn:conn.execute("UPDATE users SET role='viewer' WHERE id='local-engineer'")
        self.assertEqual(self.match(p).status_code,403)

    def test_rejected_merge_does_not_partly_rewrite_existing_engineering_data(self):
        import json
        p=self.model();a,b=[n['id'] for n in p['nodes']]
        p['analysis_model']={'elements':[{'id':'obsolete-source-record','from_point_id':a,'to_point_id':b,
            'dx_mm':'1','dy_mm':'0','dz_mm':'0','evidence':'SYNTHETIC deliberately inconsistent legacy input','verification':'proposed'}]}
        with main.db() as conn:conn.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p),p['id']))
        response=self.match(p,'ACCEPT_IDENTITY');self.assertEqual(response.status_code,409,response.text)
        current=self.client.get(f"/api/v1/projects/{p['id']}").json()
        self.assertEqual(current['version'],p['version']);self.assertEqual(len(current['nodes']),2)
        self.assertEqual(current['analysis_model'],p['analysis_model']);self.assertNotIn('point_aliases',current)

    def test_three_source_depictions_keep_one_uuid_and_supersede_old_proof(self):
        p=self.match(self.model(),'ACCEPT_IDENTITY').json();canonical=p['nodes'][0]['id']
        with fitz.open() as doc:
            doc.new_page(width=600,height=500).insert_text((50,50),'SYNTHETIC ONLY THIRD SOURCE DEPICTION')
            raw=doc.tobytes()
        p=self.upload(p,raw);sheet=p['sheets'][-1]
        response=self.client.patch(f"/api/v1/projects/{p['id']}/sheets/{sheet['id']}",json={'version':p['version'],
            'printed_id':'SHEET 3 OF 3','line_id':p['line_id'],'axis':None,'table':None,'confirm_identity':True})
        self.assertEqual(response.status_code,200,response.text);p=response.json()
        body=self.node(p,'100 mm','SYNTHETIC reviewed third source depiction')
        body.update(kind='continuation',order=2);body['instances'][0]['sheet_id']=sheet['id']
        p=self.client.post(f"/api/v1/projects/{p['id']}/nodes",json=body).json();third=p['nodes'][-1]['id']
        for axis,value in [('X','E 1000 mm'),('Y','S 500 mm'),('Z','EL 300 mm')]:
            response=self.client.post(f"/api/v1/projects/{p['id']}/physical-model/dimensions",json={'version':p['version'],
                'kind':'COORDINATE','axis':axis,'from_point_id':third,'to_point_id':None,'source_text':value,
                'tolerance_text':'0 mm','sheet_id':sheet['id'],'evidence':'SYNTHETIC independent third-page source coordinates','confirmed':True})
            self.assertEqual(response.status_code,200,response.text);p=response.json()
        response=self.match(p,'ACCEPT_IDENTITY',left_point_id=third,right_point_id=canonical);self.assertEqual(response.status_code,200,response.text);p=response.json()
        self.assertEqual(len(p['nodes']),1);self.assertEqual(p['nodes'][0]['id'],canonical)
        self.assertEqual(len(p['nodes'][0]['instances']),3);self.assertEqual(p['point_aliases'][third],canonical)
        self.assertEqual([c['status'] for c in p['continuations']],['SUPERSEDED','ACCEPTED'])
        self.assertFalse(p['nodes'][0].get('continuation_review_reasons'))
