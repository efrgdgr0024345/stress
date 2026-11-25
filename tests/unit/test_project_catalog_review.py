"""Actual627-row catalog limits plus explicitly labelled software-only matching rules."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import unittest

from packages.catalogs import normalize_record
from packages.catalogs.canonical import prepare,SOURCE_SHA256
from packages.catalogs.project_review import (catalog_review_report,prepare_catalog_review,
    record_catalog_decision,record_manufacturer_decision,refresh_project_catalog_reviews,
    manufacturer_confirmed,record_weight_values)
from tests.unit import test_source_exceptions as source_fixture
from tests.unit.test_physical_model import project,material
from tests.unit.test_catalogs import row

ROOT=Path(__file__).resolve().parents[2]
CATALOG=ROOT/'fixtures/catalogs/PIPE100_Flange_Weights_B16_5_B16_47_API6A_Numbers.xlsx'
PRIVATE_CATALOG=Path('/workspace/attachments/386a9c8e-e9c8-4027-b2dd-6256a3ed3470/PIPE100_Flange_Weights_B16_5_B16_47_API6A_Numbers.xlsx')
EVIDENCE='SOFTWARE VALIDATION ONLY: reviewed reference/source limitation, not real project engineering acceptance.'
REVIEWER='SOFTWARE-ONLY-CATALOG-REVIEWER'
WHEN='2026-11-25T00:00:00+00:00'


def real_versions():
    path=CATALOG if CATALOG.is_file() else PRIVATE_CATALOG
    assert path.is_file(),'The exact user-provided catalog is required for real627-row qualification.'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==SOURCE_SHA256
    result=[]
    for index,data in enumerate(prepare(path)):
        data.update(records_sha256=hashlib.sha256(json.dumps(data['records'],sort_keys=True).encode()).hexdigest(),
            source_filename=path.name)
        result.append({'id':'actual-source-dataset-'+str(index),'catalog_id':'actual-source-catalog',
            'source_integrity_current':True,'data':data})
    return result


def software_model(quality='REFERENCE_ONLY'):
    p=project();p.update(id='SOFTWARE-ONLY-CATALOG-VECTOR',version=1)
    m=material('software-item','flange','FLANGE WN RF CLASS150 ASME B16.5')
    p['materials']=[m];record=normalize_record(row(quality=quality,
        **({'vendor':'SOFTWARE SOURCE VENDOR','model':'SOFTWARE SOURCE MODEL'} if quality=='MANUFACTURER_CONFIRMED' else {})))
    record.update(id='SOFTWARE-ONLY-ROW',source_row=2)
    data={'records':[record],'records_sha256':hashlib.sha256(json.dumps([record],sort_keys=True).encode()).hexdigest(),
        'source_sha256':'b'*64,'status':'APPROVED','approval':{'user_id':REVIEWER,'reason':EVIDENCE},
        'units':{'weight_output':'N','length_output':'mm'},'errors':[]}
    return p,[{'id':'SOFTWARE-ONLY-DATASET','catalog_id':'SOFTWARE-ONLY-CATALOG','data':data}]


class ProjectCatalogReviewTests(unittest.TestCase):
    def real(self):return source_fixture.SourceExceptionTests().model()

    def decide(self,p,versions,row,decision='DECLARE_NA',reason='NO_EXACT_CATALOG_MATCH',**extra):
        return record_catalog_decision(p,versions,row['material_id'],decision,reason,EVIDENCE,REVIEWER,WHEN,
            row['source_context_sha256'],**extra)

    def test_actual627_rows_never_match_unproved_api_type_facing_or_valve_dimensions(self):
        p=self.real();versions=real_versions();before=deepcopy(p)
        report=catalog_review_report(p,versions)
        self.assertEqual(p,before);self.assertEqual(sum(v['record_count'] for v in report['catalog_manifest']),627)
        self.assertTrue(all(v['status']=='PENDING_APPROVAL' and v['approval'] is None for v in report['catalog_manifest']))
        self.assertEqual(len(report['rows']),6);self.assertEqual(len(report['occurrences']),18)
        self.assertEqual([len(s['rows']) for s in report['sheets']],[2,4])
        self.assertEqual(len(report['classification_rows']),1);self.assertEqual(report['classification_rows'][0]['family'],'other')
        self.assertTrue(all(not r['exact_candidates'] and not any(r['values'].values()) for r in report['rows']))
        self.assertTrue(all(r['project_manufacturer']['status']=='UNCONFIRMED' for r in report['rows']))
        flanges=[r for r in report['rows'] if r['family']=='flange']
        self.assertEqual(sum(r['occurrence_count'] for r in flanges),13)
        self.assertTrue(all('CATALOG_FACING_UNSPECIFIED' in r['reason_codes'] for r in flanges))
        self.assertTrue(all(r['source_specification'].get('api_bore') is None for r in flanges if r['size']=='8'))
        self.assertEqual(next(r for r in flanges if r['size']=='2')['source_specification']['api_bore'],'2 1/16')
        self.assertTrue(all(not c['numeric_application_allowed'] for r in flanges for c in r['partial_candidates']))

    def test_actual_na_decisions_cover_all_occurrences_without_accepting_numeric_or_model_facts(self):
        p=self.real();versions=real_versions();nodes=deepcopy(p['nodes']);physical=deepcopy(p['physical_model'])
        prepare_catalog_review(p,versions,REVIEWER,WHEN)
        report=catalog_review_report(p,versions)
        for row in report['rows']:
            self.decide(p,versions,row,reason='CATALOG_FACING_UNSPECIFIED' if row['family']=='flange' else 'VALVE_MANUFACTURER_DATA_UNAVAILABLE')
        refresh_project_catalog_reviews(p,versions);report=catalog_review_report(p,versions)
        self.assertTrue(report['summary']['review_complete']);self.assertFalse(report['summary']['numeric_complete'])
        self.assertTrue(all(r['status']=='DECLARED_NA' and r['current'] and r['color']=='blue' for r in report['rows']))
        self.assertTrue(all(not any(r['values'].values()) and not r['engineering_approved'] for r in report['occurrences']))
        self.assertEqual(p['nodes'],nodes);self.assertEqual(p['physical_model'],physical)
        self.assertTrue(all(not m.get('catalog_match') for m in p['materials']))
        row=report['rows'][0];self.decide(p,versions,row,'REOPEN','REVIEW_REOPENED')
        reopened=catalog_review_report(p,versions);target=next(r for r in reopened['rows'] if r['material_id']==row['material_id'])
        self.assertEqual(target['status'],'REOPENED');self.assertFalse(target['review_complete'])
        self.assertEqual(len([r for r in reopened['reviews'] if r['material_id']==row['material_id']]),2)

    def test_catalog_source_quality_never_confirms_actual_project_manufacturer(self):
        p,versions=software_model('MANUFACTURER_CONFIRMED');prepare_catalog_review(p,versions,REVIEWER,WHEN)
        proposed=catalog_review_report(p,versions)['rows'][0];candidate=proposed['exact_candidates'][0]
        self.decide(p,versions,proposed,'ACCEPT_EXACT_MATCH','SOURCE_SPECIFICATION_AND_DATASET_REVIEWED',
            catalog_version_id=candidate['catalog_version_id'],record_id=candidate['record_id'])
        refresh_project_catalog_reviews(p,versions);m=p['materials'][0]
        self.assertEqual(m['catalog_match']['record']['quality'],'MANUFACTURER_CONFIRMED')
        self.assertEqual(m['catalog_match']['status'],'REFERENCE_ONLY');self.assertFalse(manufacturer_confirmed(p,m,versions))
        self.assertEqual(m['project_manufacturer_status'],'UNCONFIRMED')
        current=catalog_review_report(p,versions)['rows'][0]
        record_manufacturer_decision(p,m['id'],'CONFIRM','SOFTWARE SOURCE VENDOR','SOFTWARE SOURCE MODEL',
            EVIDENCE,REVIEWER,WHEN,current['source_context_sha256'])
        self.assertTrue(manufacturer_confirmed(p,m,versions));self.assertEqual(m['catalog_match']['status'],'REFERENCE_ONLY')
        m['size']='10';self.assertFalse(manufacturer_confirmed(p,m,versions))
        self.assertEqual(catalog_review_report(p,versions)['rows'][0]['project_manufacturer']['status'],'STALE')

    def test_source_catalog_and_material_changes_stale_dispositions_and_suppress_display_values(self):
        p,versions=software_model();prepare_catalog_review(p,versions,REVIEWER,WHEN)
        r=catalog_review_report(p,versions)['rows'][0];c=r['exact_candidates'][0]
        self.decide(p,versions,r,'ACCEPT_EXACT_MATCH','SOURCE_SPECIFICATION_AND_DATASET_REVIEWED',catalog_version_id=c['catalog_version_id'],record_id=c['record_id'])
        refresh_project_catalog_reviews(p,versions)
        self.assertEqual(p['materials'][0]['catalog_review_state']['values']['weight_n'],'100')
        original=deepcopy(p)
        p['materials'][0]['quantity']=2;refresh_project_catalog_reviews(p)
        self.assertFalse(p['materials'][0]['catalog_review_state']['match_current'])
        self.assertIsNone(p['materials'][0]['catalog_review_state']['values']['weight_n'])
        p=deepcopy(original);bad=deepcopy(versions);bad[0]['source_integrity_current']=False
        refresh_project_catalog_reviews(p,bad)
        self.assertFalse(p['materials'][0]['catalog_review_state']['match_current'])
        self.assertEqual(catalog_review_report(p)['rows'][0]['status'],'REVIEW_STALE')
        self.assertEqual(p['materials'][0]['catalog_match']['record']['weight_n'],'100')

    def test_bolting_totals_scope_and_unknown_or_zero_values_stay_distinct(self):
        bare=normalize_record(row())
        self.assertEqual(record_weight_values(bare),{'weight_n':'100','half_weight_n':'140','full_weight_n':'180','length_mm':None,'assembly_weight_n':None})
        assembly=normalize_record(row(weight_scope='ASSEMBLY_INCLUDES_BOLTING',half_weight_n='140',full_weight_n='180'))
        values=record_weight_values(assembly);self.assertIsNone(values['weight_n']);self.assertEqual(values['assembly_weight_n'],'100')
        self.assertEqual(values['half_weight_n'],'140');self.assertEqual(values['full_weight_n'],'180')
        zero=normalize_record(row(weight_n='0',weight_scope='UNKNOWN',studs_weight_n=None,nut_weight_n=None,stud_count=None))
        self.assertTrue(all(v is None for v in record_weight_values(zero).values()))

    def test_legacy_reference_refresh_cannot_resurrect_a_live_failed_catalog_from_its_snapshot(self):
        p,versions=software_model();m=p['materials'][0];data=versions[0]['data']
        m['catalog_match']={'catalog_version_id':versions[0]['id'],'catalog_source_sha256':data['source_sha256'],
            'catalog_records_sha256':data['records_sha256'],'catalog_approval':data['approval'],'record':deepcopy(data['records'][0])}
        refresh_project_catalog_reviews(p,versions)
        self.assertTrue(m['catalog_review_state']['match_current'])
        from packages.catalogs.project_review import source_context,digest
        record_manufacturer_decision(p,m['id'],'CONFIRM','SOFTWARE-ONLY INSTALLED MAKER',
            'SOFTWARE-ONLY INSTALLED MODEL',EVIDENCE,REVIEWER,WHEN,digest(source_context(p,m)))
        self.assertTrue(manufacturer_confirmed(p,m,versions))
        failed=deepcopy(versions);failed[0]['source_integrity_current']=False
        refresh_project_catalog_reviews(p,failed)
        self.assertFalse(m['catalog_review_state']['match_current'])
        self.assertEqual(m['project_manufacturer_status'],'STALE')
        refresh_project_catalog_reviews(p)
        self.assertFalse(m['catalog_review_state']['match_current'])
        self.assertEqual(m['project_manufacturer_status'],'STALE')
        self.assertFalse(manufacturer_confirmed(p,m))

    def test_na_and_manufacturer_reopen_are_source_bound_and_never_approve_catalogs(self):
        p=self.real();versions=real_versions();prepare_catalog_review(p,versions,REVIEWER,WHEN)
        r=catalog_review_report(p,versions)['rows'][0];self.decide(p,versions,r)
        record_manufacturer_decision(p,r['material_id'],'REOPEN',None,None,EVIDENCE,REVIEWER,WHEN,r['source_context_sha256'])
        self.assertFalse(manufacturer_confirmed(p,next(m for m in p['materials'] if m['id']==r['material_id']),versions))
        changed=deepcopy(versions);changed[0]['data']['status']='APPROVED';changed[0]['data']['approval']={'user_id':REVIEWER,'reason':EVIDENCE}
        self.assertEqual(catalog_review_report(p,changed)['rows'][0]['status'],'REVIEW_STALE')
        m=next(m for m in p['materials'] if m['id']==r['material_id']);m['source_bbox'][0]+=1
        self.assertEqual(catalog_review_report(p,versions)['rows'][0]['status'],'REVIEW_STALE')
        with self.assertRaisesRegex(ValueError,'context changed'):
            self.decide(p,versions,r,'REOPEN','REVIEW_REOPENED')
        self.assertTrue(all(v['data']['status']=='PENDING_APPROVAL' and v['data']['approval'] is None for v in versions))
