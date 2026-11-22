"""Excel file structure, literal text, exact values and element API invariants."""
import io
import json
import unittest
import zipfile
from unittest.mock import patch

from openpyxl import load_workbook
from packages.workbooks import workbook,tables
from services.api import main,pipeline
from tests.integration import test_api as fixtures
from tests.integration.test_pipeline import drawing,native_executor
from packages.workbooks.csv_export import csv_bundle
from tests.unit.test_neutral_export import model as native_model,sections,numbers


class WorkbookTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    def prepared(self):
        p=self.client.post('/api/v1/projects',json={'title':'Excel regression','line_id':'AUTO-TEST-001'}).json()
        self.client.post(f"/api/v1/projects/{p['id']}/intake?version=1",content=drawing(),headers={'Content-Type':'application/pdf','X-Filename':'native.pdf'})
        with patch.object(pipeline,'execute',side_effect=native_executor):
            while pipeline.process_one(main):pass
        return self.client.get(f"/api/v1/projects/{p['id']}").json()

    def test_working_xlsx_numeric_cells_tables_freeze_and_blank_unknowns(self):
        p=self.prepared();response=self.client.get(f"/api/v1/projects/{p['id']}/results/workbook")
        self.assertEqual(response.status_code,200,response.text[:200] if response.status_code!=200 else '')
        book=load_workbook(io.BytesIO(response.content),data_only=False)
        self.assertIn('CAESAR input',book.sheetnames);self.assertIn('CAESAR readiness',book.sheetnames)
        self.assertEqual(book['Nodes']['A6'].value,10);self.assertIsNone(book['Nodes']['E7'].value)
        self.assertEqual(book['Nodes']['O7'].value,50)
        self.assertIsNone(book['CAESAR input']['E6'].value) # signed DX unknown, not scaled or zero
        self.assertEqual(book['Nodes'].freeze_panes,'C6');self.assertTrue(book['Nodes'].tables)
        self.assertTrue(book['CAESAR input'].data_validations.dataValidation)
        self.assertFalse(book['Nodes'].protection.sheet)
        for sheet in book:
            self.assertFalse(any(c.data_type=='f' for row in sheet for c in row))
        book['Nodes']['E6']=12.7
        saved=io.BytesIO();book.save(saved);book.close()
        reopened=load_workbook(io.BytesIO(saved.getvalue()),data_only=False)
        self.assertEqual(reopened['Nodes']['E6'].value,12.7);reopened.close()

    def test_user_text_is_literal_and_exact_decimal_text_is_retained(self):
        p=self.prepared();p['title']='=HYPERLINK("https://example.invalid", "unsafe")'
        p['nodes'][0]['evidence']='=1+1';p['nodes'][0]['station_mm']='123.123456789123456789'
        data=workbook(p)
        book=load_workbook(io.BytesIO(data),data_only=False)
        self.assertEqual(book['Nodes']['A1'].data_type,'s');self.assertTrue(book['Nodes']['A1'].value.startswith('='))
        self.assertEqual(book['Nodes']['L6'].data_type,'s');self.assertEqual(book['Nodes']['L6'].value,'=1+1')
        values=[r[3] for r in book['Exact values'].iter_rows(min_row=2,values_only=True)]
        self.assertIn('123.123456789123456789',values);book.close()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertFalse(any('vbaProject' in n or 'externalLinks/' in n for n in archive.namelist()))

    def test_unrepresentable_excel_values_fail_instead_of_becoming_zero(self):
        p=self.prepared();p['nodes'][0]['station_mm']='1e-9999'
        with self.assertRaisesRegex(ValueError,'numeric range'):workbook(p)

    def test_element_properties_are_evidence_backed_and_do_not_change_stations(self):
        p=self.prepared();data=self.client.get(f"/api/v1/projects/{p['id']}/results").json()
        element=next(t for t in data['tables'] if t['name']=='CAESAR input')['rows'][0]
        payload={'version':p['version'],'dx_mm':'1000','dy_mm':'0','dz_mm':'-50.8','od_mm':'219.1','wall_mm':'8.18','corrosion_mm':'3','material_code':'106','temperature_c':'80','pressure_mpa':'1.25','evidence':'Synthetic property evidence for regression only'}
        response=self.client.patch(f"/api/v1/projects/{p['id']}/results/elements/{element['id']}",json=payload)
        self.assertEqual(response.status_code,200,response.text);new=response.json()
        self.assertEqual([n['station_mm'] for n in new['nodes']],[n['station_mm'] for n in p['nodes']])
        data=self.client.get(f"/api/v1/projects/{p['id']}/results").json();self.assertFalse(data['caesar']['direct_import_ready'])
        gate=next(g for g in data['caesar']['gates'] if g['gate']=='Element geometry and properties')
        self.assertFalse(gate['passed']);self.assertIn('1 of 3',gate['detail'])
        row=next(t for t in data['tables'] if t['name']=='CAESAR input')['rows'][0]
        self.assertEqual(row['dz'],'-50.8');self.assertEqual(row['pressure'],'1.25')
        payload.update(version=new['version'],wall_mm='120')
        self.assertEqual(self.client.patch(f"/api/v1/projects/{p['id']}/results/elements/{element['id']}",json=payload).status_code,422)

    def test_workbook_in_automatic_artifact_is_revision_bound_and_private(self):
        p=self.prepared();run=self.client.get(f"/api/v1/projects/{p['id']}/pipeline").json()['runs'][0]
        artifact=run['progress']['artifact']
        response=self.client.get(f"/api/v1/projects/{p['id']}/artifacts/{artifact['id']}/workbook")
        self.assertEqual(response.status_code,200);book=load_workbook(io.BytesIO(response.content));self.assertEqual(book['Read me']['B6'].value,str(p['version']));book.close()
        with main.db() as conn:conn.execute("UPDATE projects SET tenant='other' WHERE id=?",(p['id'],))
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}/artifacts/{artifact['id']}/workbook").status_code,404)

    def test_csv_is_numeric_interchange_and_text_formulas_stay_literal(self):
        p=self.prepared();p['nodes'][0]['evidence']='=HYPERLINK("https://example.invalid")'
        data=csv_bundle(p)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            text=z.read('nodes.csv').decode('utf-8-sig');self.assertIn("'=HYPERLINK",text)
            self.assertIn('caesar-input.csv',z.namelist());self.assertIn('manifest.json',z.namelist())
        response=self.client.get(f"/api/v1/projects/{p['id']}/results/csv")
        self.assertEqual(response.status_code,200)
        response=self.client.get(f"/api/v1/projects/{p['id']}/results/caesar-neutral")
        self.assertEqual(response.status_code,422)

    def test_pipe_length_quantity_is_not_coerced_to_component_count(self):
        p=self.prepared();m=p['materials'][0]
        body={**m,'version':p['version'],'family':'pipe','quantity':None,'quantity_value':'44.9','quantity_unit':'m','observed_quantity_value':'44.9','evidence':'Synthetic source length unit and dimension reconciliation evidence'}
        response=self.client.patch(f"/api/v1/projects/{p['id']}/materials/{m['id']}",json=body)
        self.assertEqual(response.status_code,200,response.text)
        item=next(v for v in response.json()['materials'] if v['id']==m['id'])
        self.assertIsNone(item['quantity']);self.assertEqual(item['quantity_value'],'44.9');self.assertEqual(item['quantity_unit'],'m')

    def test_native_download_and_explicit_settings_are_revision_protected(self):
        p=self.client.post('/api/v1/projects',json={'title':'Native HTTP test','line_id':'SOFTWARE-TEST-001'}).json()
        complete=native_model();complete['id']=p['id'];complete['version']=p['version']
        from packages.automation.recognize import identity
        complete['analysis_model']['elements'][0]['id']=identity(p['id'],'point-0','point-1')
        with main.db() as conn:conn.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(complete),p['id']))
        check=self.client.get(f"/api/v1/projects/{p['id']}/results").json()
        self.assertTrue(check['native']['available']);self.assertFalse(check['native']['qualified_application_roundtrip'])
        response=self.client.get(f"/api/v1/projects/{p['id']}/results/caesar-neutral")
        self.assertEqual(response.status_code,200,response.text[:200]);self.assertIn('.cii',response.headers['content-disposition'])
        self.assertIn('windows-1252',response.headers['content-type'])
        self.assertEqual(numbers(sections(response.content)['CONTROL'][:1]),[1,0,0,0,0,0])
        body={'version':1,'piping_code_id':3,'ambient_temperature_c':'20','vertical_axis':'Z','local_origin_confirmed':True,'origin_point_id':'point-0'}
        self.assertEqual(self.client.patch(f"/api/v1/projects/{p['id']}/results/settings",json=body).status_code,200)
        self.assertEqual(self.client.patch(f"/api/v1/projects/{p['id']}/results/settings",json=body).status_code,409)
        with main.db() as conn:conn.execute("UPDATE projects SET tenant='other' WHERE id=?",(p['id'],))
        self.assertEqual(self.client.get(f"/api/v1/projects/{p['id']}/results/caesar-neutral").status_code,404)
