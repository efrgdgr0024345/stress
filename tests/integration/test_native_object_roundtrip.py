"""All generated object types on the real reviewed source, using a PDF library.

This is not the missing golden model or an Adobe/Foxit application qualification.
"""
from pathlib import Path
from copy import deepcopy
from collections import Counter
import hashlib
import io
import json
import unittest
import zipfile
import fitz
from packages.pdf import content_hash,export_bundle
from tests.integration import test_api as fixtures

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'


class NativeObjectRoundtripTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload
    node=fixtures.ApiTests.node

    def test_all_added_native_objects_can_be_selected_edited_and_reopened_on_both_sheets(self):
        p=self.upload(self.create(),SOURCE.read_bytes())
        body=self.node(p,'','SOFTWARE TEST ONLY: unverified graphic anchor, no engineered station or identity claim.')
        body.update(kind='continuation',instances=[{'sheet_id':s['id'],'anchor':[900,405],'bubble':[840,370]} for s in p['sheets']])
        r=self.client.post(f"/api/v1/projects/{p['id']}/nodes",json=body)
        self.assertEqual(r.status_code,200,r.text);p=r.json();point=p['nodes'][0]['id']
        for sheet in p['sheets']:
            r=self.client.patch(f"/api/v1/projects/{p['id']}/sheets/{sheet['id']}",json={'version':p['version'],
                'printed_id':'SOFTWARE QA ONLY','line_id':p['line_id'],'axis':[200,500],'table':[60,800]})
            self.assertEqual(r.status_code,200,r.text);p=r.json()
            r=self.client.post(f"/api/v1/projects/{p['id']}/materials",json={'version':p['version'],'sheet_id':sheet['id'],
                'item_no':'QA','family':'flange','description':'SYNTHETIC SOFTWARE NOTE — NOT SOURCE INVENTORY','size':'8',
                'quantity':1,'observed':0,'evidence':'SOFTWARE QA ONLY, unknown physical properties'})
            self.assertEqual(r.status_code,200,r.text);p=r.json()
            for index,kind in enumerate(('FreeText','Line','Circle','Square')):
                y=200+index*70
                r=self.client.post(f"/api/v1/projects/{p['id']}/annotations",json={'version':p['version'],'sheet_id':sheet['id'],
                    'kind':kind,'rect':[60,y,330,y+45],'text':'SOFTWARE QA ONLY','color':'#007aff'})
                self.assertEqual(r.status_code,200,r.text);p=r.json()
        artifact=self.client.post(f"/api/v1/projects/{p['id']}/exports",json={'version':p['version']})
        self.assertEqual(artifact.status_code,200,artifact.text)
        raw=self.client.get(f"/api/v1/projects/{p['id']}/artifacts/{artifact.json()['id']}/download").content
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            manifest=json.loads(z.read('annotation-manifest.json'));pdf=z.read('annotated-review.pdf')
        names={r['name']:r for r in manifest}
        self.assertEqual(len(names),len(manifest))
        self.assertTrue(all('physical_point_id' in r for r in manifest))
        for r in manifest:
            if r['role'] in ('number','bubble','leader'):self.assertEqual(r['physical_point_id'],point)
            else:self.assertIsNone(r['physical_point_id'])
        edited=set()
        with fitz.open(stream=pdf,filetype='pdf') as doc,fitz.open(SOURCE) as original:
            for page in doc:
                generated=[a for a in page.annots() if a.info.get('id') in names]
                self.assertTrue({'FreeText','Line','Circle','Square'}<={a.type[1] for a in generated})
                for a in generated:
                    name=a.info['id'];edited.add(name)
                    a.set_info(title='SOFTWARE ROUNDTRIP QA',subject=a.info.get('subject',''))
                    if a.type[1]=='FreeText':
                        a.set_info(content='QA '+a.info.get('content',''))
                        a.update(text_color=(.2,.1,.7))
                    else:
                        a.set_colors(stroke=(.2,.1,.7));a.set_border(width=1.4);a.update()
                self.assertEqual(content_hash(page),content_hash(original[page.number]))
            reopened_bytes=doc.tobytes(garbage=4,deflate=True)
        self.assertEqual(edited,set(names))
        with fitz.open(stream=reopened_bytes,filetype='pdf') as reopened,fitz.open(SOURCE) as original:
            seen=set()
            for page in reopened:
                for a in page.annots():
                    if a.info.get('id') not in names:continue
                    seen.add(a.info['id']);self.assertEqual(a.info['title'],'SOFTWARE ROUNDTRIP QA')
                    self.assertEqual(a.type[1],names[a.info['id']]['type'])
                    if a.type[1]=='FreeText':self.assertTrue(a.info['content'].startswith('QA '))
                    else:self.assertAlmostEqual(a.border['width'],1.4,places=4)
                self.assertEqual(content_hash(page),content_hash(original[page.number]))
            self.assertEqual(seen,edited)
        # A review PDF imported as a new source can carry the earlier object's
        # /NM. Preserve that source layer and give each newly added object an
        # unambiguous identity; external override reconciliation remains open.
        imported=Path(self.temp.name)/'imported-review.pdf';imported.write_bytes(pdf)
        repeat=deepcopy(p);repeat['version']+=1
        for s in repeat['sheets']:s['sha256']=hashlib.sha256(pdf).hexdigest()
        output=Path(self.temp.name)/'second-review.zip'
        export_bundle(repeat,lambda _:imported,output)
        with zipfile.ZipFile(output) as z:
            new_manifest=json.loads(z.read('annotation-manifest.json'))
            with fitz.open(stream=z.read('annotated-review.pdf'),filetype='pdf') as doc:
                counts=Counter(a.info.get('id') for page in doc for a in page.annots())
                self.assertTrue(all(counts[row['name']]==1 for row in new_manifest))
                self.assertTrue(set(names).isdisjoint({row['name'] for row in new_manifest}))
                with fitz.open(imported) as source:
                    for i,page in enumerate(doc):self.assertEqual(content_hash(page),content_hash(source[i]))
