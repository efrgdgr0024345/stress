"""Known workbook preparation, missing dimension metadata and approval boundaries."""
import hashlib
import io
import json
from pathlib import Path
import unittest
from openpyxl import Workbook
from tests.integration import test_api as fixtures
from services.api import main
from packages.catalogs import exact_match
from packages.catalogs.canonical import NUMBERS, SHEETS


def workbook():
    book = Workbook(write_only=True)
    for name in SHEETS:
        sheet = book.create_sheet(name)
        size = 'API bore (in)' if name == 'API 6A' else 'NPS (in)'
        rating = 'Rating (psi)' if name == 'API 6A' else 'Class'
        values = {size: '7 1/16' if name == 'API 6A' else '8', rating: 10000 if name == 'API 6A' else 150,
                  'Flange type': 'WN', 'Flange weight (N)': 100, 'Studs (count)': 2,
                  'Stud length (mm)': 50, 'Studs, full (N)': 4, 'Nut weight per nut (N)': 2,
                  'Flange + half studs + 1 nut/stud (N)': 106,
                  'Flange + all studs + 2 nuts/stud (N)': 112,
                  'Stud data source URL': 'https://source.example.invalid/studs',
                  'Flange weight source URL': 'https://source.example.invalid/flanges',
                  'Flange weight basis': 'ESTIMATE: synthetic fixture'}
        sheet.append(list(values));sheet.append(list(values.values()))
        sheet.append([v if k != size else '3 1/8' if name == 'API 6A' else '2' for k, v in values.items()])
    output = io.BytesIO();book.save(output)
    return output.getvalue()


class CanonicalCatalogTests(unittest.TestCase):
    setUp = fixtures.ApiTests.setUp
    tearDown = fixtures.ApiTests.tearDown

    def register(self):
        response = self.client.post('/api/v1/catalogs/import', files={
            'file': ('reference.xlsx', workbook(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_all_sheets_are_prepared_idempotently_with_source_provenance_and_pending_approval(self):
        source = self.register()
        response = self.client.post(f"/api/v1/catalogs/{source['id']}/prepare")
        self.assertEqual(response.status_code, 200, response.text)
        datasets = response.json()
        self.assertEqual(len(datasets), 4)
        self.assertEqual([len(d['data']['records']) for d in datasets], [2,2,2,2])
        self.assertTrue(all(d['data']['status'] == 'PENDING_APPROVAL' and d['data']['approval'] is None for d in datasets))
        self.assertEqual([d['id'] for d in self.client.post(f"/api/v1/catalogs/{source['id']}/prepare").json()], [d['id'] for d in datasets])
        record = datasets[-1]['data']['records'][0]
        self.assertEqual(record['api_bore'], '7 1/16')
        self.assertEqual(record['nps'], '')
        self.assertEqual(record['facing'], 'UNSPECIFIED')
        self.assertEqual(record['quality'], 'ESTIMATED')
        self.assertEqual(record['full_weight_n'], '112')
        self.assertEqual(record['source_fields']['Flange weight (N)'], 100)
        self.assertEqual(record['source_sha256'], source['sha256'])
        self.assertEqual(self.client.get('/api/v1/approved-catalogs').json(), [])
        exact = exact_match([record], {'family':'flange','standard':'API 6A','api_bore':'7 1/16','nps':'8','rating':'10000','component_type':'WN','facing':'RTJ'})
        self.assertEqual(exact['status'], 'NO_EXACT_MATCH')
        path = main.DATA / 'catalogs' / f"{source['id']}.xlsx"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source['sha256'])

    def test_manual_mapper_reads_all_columns_and_rows_without_xlsx_dimension_tags(self):
        source = self.register()
        preview = self.client.get(f"/api/v1/catalogs/{source['id']}/preview?sheet=B16.5").json()
        self.assertIn('Flange weight basis', [v['label'] for v in preview['headers']])
        headers = {v['label']: v['index'] for v in preview['headers']}
        response = self.client.post(f"/api/v1/catalogs/{source['id']}/versions", json={
            'sheet':'B16.5', 'columns': {'nps':headers['NPS (in)'],'rating':headers['Class'],'component_type':headers['Flange type'],'weight_n':headers['Flange weight (N)']},
            'constants': {'family':'flange','standard':'ASME B16.5','quality':'ESTIMATED','source':'Synthetic test','facing':'RF'},
            'weight_unit':'N','length_unit':'mm'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()['data']['records']), 2)

    def test_tenant_editor_and_source_integrity_are_enforced(self):
        source = self.register()
        with main.db() as conn:conn.execute("UPDATE users SET role='engineer' WHERE id='local-engineer'")
        self.assertEqual(self.client.post(f"/api/v1/catalogs/{source['id']}/prepare").status_code, 403)
        with main.db() as conn:
            conn.execute("UPDATE users SET role='admin' WHERE id='local-engineer'")
            conn.execute('UPDATE catalogs SET tenant=? WHERE id=?', ('other', source['id']))
        self.assertEqual(self.client.post(f"/api/v1/catalogs/{source['id']}/prepare").status_code, 404)
