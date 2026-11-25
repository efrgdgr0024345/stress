"""One exact real-source revision supplies every review artifact and CSV table."""
import csv
import io
import json
import unittest
import zipfile
from openpyxl import load_workbook
from tests.integration import test_api as fixtures
from tests.integration import test_1010_source_review as source_fixtures


class RealPacketTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload
    source=source_fixtures.SourceReviewTests.source
    prepare=source_fixtures.SourceReviewTests.prepare

    def test_complete_packet_keeps_real_unknowns_blank_and_incomplete_cii_blocked(self):
        p=self.prepare(self.source());path=f"/api/v1/projects/{p['id']}"
        response=self.client.post(path+'/exports',json={'version':p['version']})
        self.assertEqual(response.status_code,200,response.text);artifact=response.json()
        response=self.client.get(path+f"/artifacts/{artifact['id']}/download")
        self.assertEqual(response.status_code,200,response.text[:200] if response.status_code!=200 else '')
        with zipfile.ZipFile(io.BytesIO(response.content)) as packet:
            self.assertEqual(len(packet.namelist()),len(set(packet.namelist())))
            required={'annotated-review.pdf','engineering-workbook.xlsx','project.json','annotation-manifest.json',
                'exceptions.json','numbering-map.json','numbering-history.json','native-layout.json',
                'station-solution.json','topology-review.json','source-exceptions.json','catalog-review.json',
                'continuation-review.json','source-evidence.json','caesar-readiness.json','csv/manifest.json'}
            self.assertTrue(required<=set(packet.namelist()))
            snapshot=json.loads(packet.read('project.json'));csv_manifest=json.loads(packet.read('csv/manifest.json'))
            self.assertEqual(snapshot['id'],p['id']);self.assertEqual(snapshot['version'],p['version'])
            self.assertEqual(csv_manifest['revision'],p['version'])
            book=load_workbook(io.BytesIO(packet.read('engineering-workbook.xlsx')),read_only=True,data_only=True)
            def rows(name):return list(csv.DictReader(io.StringIO(packet.read('csv/'+name+'.csv').decode('utf-8-sig'))))
            nodes=rows('nodes');ports=rows('component-ports')
            self.assertEqual(len(nodes),47);self.assertEqual(len(ports),60)
            self.assertTrue(all(r['Node']=='' and r['Accepted station (mm)']=='' for r in nodes))
            self.assertEqual(book['Nodes'].max_row-5,len(nodes));self.assertEqual(book['Component ports'].max_row-5,len(ports))
            self.assertEqual(len(rows('catalog-schedules')),6);self.assertEqual(len(rows('catalog-occurrences')),18)
            for row in rows('catalog-schedules'):
                self.assertEqual(row['W_flange / valve weight (N)'],'');self.assertEqual(row['Valve length (mm)'],'')
            for table in json.loads(self.client.get(path+'/results').content)['tables']:
                csv_name=table['name'].lower().replace(' ','-')
                self.assertEqual(len(rows(csv_name)),len(table['rows']),table['name'])
            source=json.loads(packet.read('source-evidence.json'))
            self.assertEqual({s['sha256'] for s in source['sheets']},{'7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59'})
            native=json.loads(packet.read('caesar-readiness.json'))
            self.assertFalse(native['available']);self.assertTrue(native['missing'])
            self.assertNotIn('caesar-import-candidate.cii',packet.namelist())
            self.assertTrue(json.loads(packet.read('qa.json'))['source_content_unchanged'])
            book.close()
