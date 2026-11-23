"""Thirteen NEW plan acceptance checks, not the unavailable 13 legacy tests.

Intentionally fail without authoritative originals and actual candidate outputs.
The isolated legacy runner must be restored from the original archive, after
its layout/dependencies are inspected. No replacement original tests are invented.
"""
import hashlib
import json
from pathlib import Path
import sys
import os
import subprocess
import tempfile
from decimal import Decimal
import unittest

import fitz

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.audit_1010_golden import audit,safe_file
from packages.pdf import content_hash

FIXTURE=ROOT/'fixtures/1010'
OUTPUT=ROOT/'.local/1010-golden'


class Golden1010Acceptance(unittest.TestCase):
    def originals(self):
        result=audit()
        missing=[r['role'] for r in result['assets'] if not r['ready']]
        self.assertEqual(missing,[],f'Original assets/trusted hashes missing: {missing}. Reviewed/synthetic substitutes are forbidden.')
        return {r['role']:safe_file(FIXTURE,r['path']) for r in result['assets']}

    def candidate(self):
        self.originals()
        path=OUTPUT/'project.json'
        self.assertTrue(path.is_file(),'Actual application candidate project has not been generated from the original fixture.')
        return json.loads(path.read_text())

    def test_01_all_original_assets_have_trusted_sha256_pins(self):
        self.originals()

    def test_02_original_thirteen_tests_are_restored_and_actually_run(self):
        self.originals()
        # Require the restored CI runner, not a manually supplied pass receipt.
        runner=ROOT/'legacy/1010/run_original_tests.py'
        self.assertTrue(runner.is_file(),'Original suite/isolated runner unavailable. These new acceptance checks do not replace its 13 tests.')
        # Only reviewed repository runner code may execute the authentic tests.
        # A supplied JSON receipt is not used as proof that the suite ran.
        with tempfile.TemporaryDirectory(prefix='legacy-1010-') as work:
            result=subprocess.run([sys.executable,str(runner),'--isolated','--json'],cwd=work,
                env={'PATH':os.environ.get('PATH',''),'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=240)
        self.assertEqual(result.returncode,0,'Actual isolated legacy suite failed')
        receipt=json.loads(result.stdout)
        self.assertEqual(receipt['tests_run'],13);self.assertEqual(len(set(receipt['test_ids'])),13)
        self.assertEqual([receipt[k] for k in ('failures','errors','skipped')],[0,0,0])
        self.assertEqual(receipt['archive_sha256'],audit()['assets'][0]['expected_sha256'])
        self.assertTrue(receipt['isolated'])

    def test_03_original_source_is_two_sheets_on_the_same_full_line(self):
        assets=self.originals();p=self.candidate()
        with fitz.open(assets['original_pdf']) as doc:self.assertEqual(len(doc),2)
        self.assertEqual(len(p['sheets']),2)
        self.assertEqual({s['line_id'] for s in p['sheets']},{'8-PG-JE3LN2-1010-FUTURE'})
        original_sha=hashlib.sha256(assets['original_pdf'].read_bytes()).hexdigest()
        self.assertEqual({s['sha256'] for s in p['sheets']},{original_sha})

    def test_04_exactly_48_unique_physical_points(self):
        nodes=self.candidate()['nodes']
        self.assertEqual(len(nodes),48);self.assertEqual(len({n['id'] for n in nodes}),48)

    def test_05_exactly_49_displayed_labels(self):
        self.assertEqual(sum(len(n['instances']) for n in self.candidate()['nodes']),49)

    def test_06_node_170_has_one_identity_on_both_sheets(self):
        nodes=[n for n in self.candidate()['nodes'] if n['number']==170]
        self.assertEqual(len(nodes),1);self.assertEqual(len({i['sheet_id'] for i in nodes[0]['instances']}),2)

    def test_07_main_series_is_10_through_370(self):
        self.assertEqual(sorted(n['number'] for n in self.candidate()['nodes'] if n['route']=='main'),list(range(10,371,10)))

    def test_08_branch_series_are_400_500_600(self):
        p=self.candidate();routes={n['route'] for n in p['nodes']}-{'main'}
        actual=sorted(sorted(n['number'] for n in p['nodes'] if n['route']==r) for r in routes)
        self.assertEqual(actual,[list(range(400,431,10)),list(range(500,531,10)),list(range(600,621,10))])

    def test_09_material_counts_match_the_specific_golden_drawing(self):
        p=self.candidate();sheets=sorted(p['sheets'],key=lambda s:s['page_index'])
        count=lambda family,sheet:sum(m['quantity'] for m in p['materials'] if m['family']==family and m['sheet_id']==sheet['id'])
        self.assertEqual([count('flange',s) for s in sheets],[4,9])
        self.assertEqual(sum(count('tee',s) for s in sheets),3)
        self.assertEqual(sum(count('elbow',s) for s in sheets),5)
        self.assertEqual(sum(count('valve',s) for s in sheets),5)
        second=[m for m in p['materials'] if m['family']=='flange' and m['sheet_id']==sheets[1]['id']]
        self.assertEqual(sum(m['quantity'] for m in second if m['size'].strip('" ' )=='8'),6)
        self.assertEqual(sum(m['quantity'] for m in second if m['size'].strip('" ' )=='2'),3)
        valves=[m for m in p['materials'] if m['family']=='valve']
        ball=[m for m in valves if 'BALL' in m['description'].upper()]
        dbb=[m for m in valves if 'DBB' in m['description'].upper()]
        self.assertEqual(sum(m['quantity'] for m in ball),2);self.assertEqual(sum(m['quantity'] for m in dbb),3)
        for m in ball:
            match=m.get('catalog_match') or {};record=match.get('record') or {}
            self.assertEqual(Decimal(str(record.get('length_mm'))),Decimal('889'))
            self.assertEqual(Decimal(str(record.get('weight_n'))),Decimal('13729.31'))
            self.assertNotEqual(match.get('status'),'MANUFACTURER_CONFIRMED')
        for m in dbb:
            record=(m.get('catalog_match') or {}).get('record') or {}
            self.assertIsNone(record.get('length_mm'));self.assertIsNone(record.get('weight_n'))

    def test_10_accepted_points_stations_and_colour_reasons_match_reviewed_oracle(self):
        p=self.candidate();path=OUTPUT/'reviewed-oracle.json'
        self.assertTrue(path.is_file(),'Actual legacy schemas require a reviewed adapter; no oracle has been fabricated.')
        oracle=json.loads(path.read_text());pins={r['role']:r['expected_sha256'] for r in audit()['assets']}
        self.assertEqual(oracle['source_sha256'],pins)
        fields=('id','number','station_mm','reasons')
        signature=lambda nodes:sorted([{k:n[k] for k in fields} for n in nodes],key=lambda n:n['id'])
        self.assertEqual(signature(p['nodes']),signature(oracle['project']['nodes']))

    def test_11_component_interfaces_have_current_physical_proof(self):
        from packages.physical import audit as physical_audit
        p=self.candidate();result=physical_audit(p)
        self.assertEqual(result['issues'],[])
        self.assertTrue(result['components'])
        self.assertTrue(all(n.get('station_mm') is not None and n.get('evidence') and n.get('verification')!='proposed' for n in p['nodes']))

    def test_12_original_streams_and_native_addition_count_are_preserved(self):
        assets=self.originals();self.candidate();path=OUTPUT/'review.pdf'
        self.assertTrue(path.is_file(),'Actual native candidate PDF missing')
        with fitz.open(assets['original_pdf']) as source,fitz.open(assets['golden_pdf']) as golden,fitz.open(path) as candidate:
            self.assertEqual(len(candidate),len(source));self.assertEqual(len(golden),len(source))
            additions=0;golden_additions=0
            for before,expected,after in zip(source,golden,candidate):
                self.assertEqual(content_hash(before),content_hash(after))
                baseline=len(list(before.annots() or []))
                additions+=len(list(after.annots() or []))-baseline
                golden_additions+=len(list(expected.annots() or []))-baseline
            self.assertEqual(golden_additions,297);self.assertEqual(additions,golden_additions)

    def test_13_every_added_native_object_has_a_manifest_identity(self):
        p=self.candidate();assets=self.originals();manifest_path=OUTPUT/'annotation-manifest.json'
        self.assertTrue(manifest_path.is_file(),'Native object manifest missing')
        manifest=json.loads(manifest_path.read_text());self.assertEqual(len(manifest),297)
        self.assertEqual(len({r['name'] for r in manifest}),len(manifest))
        actual={};sheet_ids={s['page_index']:s['id'] for s in p['sheets']}
        with fitz.open(assets['original_pdf']) as original,fitz.open(OUTPUT/'review.pdf') as doc:
            for index,page in enumerate(doc):
                baseline={a.info.get('id') for a in original[index].annots() or []}
                for a in page.annots() or []:
                    name=a.info.get('id')
                    if name not in baseline:
                        self.assertTrue(name);self.assertNotIn(name,actual)
                        actual[name]=(sheet_ids[index],a.type[1])
        self.assertEqual(set(actual),{r['name'] for r in manifest})
        nodes={n['id'] for n in p['nodes']}
        for row in manifest:
            self.assertEqual(actual[row['name']],(row['sheet_id'],row['type']));self.assertTrue(row['role'])
            if row['role'] in ('bubble','leader','number'):
                self.assertIn(row.get('physical_point_id',row.get('group')),nodes)
        expected={(n['id'],i['sheet_id']) for n in p['nodes'] for i in n['instances']}
        for role in ('bubble','leader','number'):
            displayed=[(r.get('physical_point_id',r.get('group')),r['sheet_id']) for r in manifest if r['role']==role]
            self.assertEqual(len(displayed),49);self.assertEqual(set(displayed),expected)
