"""Exact-source graphical review/edit proof; no physical model values are accepted."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
import zipfile

import fitz
from packages.engineering import validate
from packages.pdf import (plan_layout,apply_layout,accepted_plan_current,layout_input_sha256,
    export_bundle,content_hash,raw_content_hash,source_annotation_snapshot)
from tests.unit import test_source_exceptions as source_fixture

SOURCE=source_fixture.SOURCE


class RealNativeLayoutTests(unittest.TestCase):
    def model(self):
        p=source_fixture.SourceExceptionTests().model()
        p['title']='SOFTWARE ONLY actual-source native graphic review'
        p['issues']=validate(p)
        return p

    def test_all47_are_source_safe_and_graphic_acceptance_is_stable_without_engineering_changes(self):
        p=self.model();before=deepcopy(p);plan=plan_layout(p,lambda _:SOURCE)
        self.assertEqual(p,before);self.assertTrue(plan['can_export'],plan['issues'])
        self.assertEqual(plan['summary']['point_instances'],47)
        self.assertTrue(all(v['leader_vertices'] for s in plan['sheets'] for v in s['point_positions']))
        objects=[v for s in plan['sheets'] for v in s['placements']]
        self.assertEqual(len([v for v in objects if v['role']=='point-warning']),47)
        self.assertEqual(len([v for v in objects if v['role']=='source-warning' and 'UNCONFIRMED_ELBOW_COD' in v.get('reason_codes',[])]),5)
        self.assertEqual(len([v for v in objects if v['role']=='source-warning' and 'INSTRUMENT_CLASSIFICATION_REVIEW_REQUIRED' in v.get('reason_codes',[])]),1)
        self.assertTrue(all(v['physical_point_id'] is None for v in objects if 'UNCONFIRMED_ELBOW_COD' in v.get('reason_codes',[])))
        self.assertTrue(all(v.get('source_evidence') and v.get('reason_codes') for v in objects if v['role']=='point-warning'))
        crossings=[c for s in plan['sheets'] for c in s['allowed_source_annotation_crossings']]
        self.assertGreater(len(crossings),0);self.assertLessEqual(len(crossings),3)
        self.assertTrue(all(c.get('physical_point_id') and not c.get('original_annotation_modified') for c in crossings))
        apply_layout(p,plan,'SOFTWARE-ONLY-GRAPHIC-REVIEWER','2026-11-25',
            'SOFTWARE VALIDATION ONLY: graphical placement accepted; no engineering facts approved.')
        again=plan_layout(p,lambda _:SOURCE)
        self.assertTrue(accepted_plan_current(p,again));self.assertEqual(plan['placements_sha256'],again['placements_sha256'])
        for old,node in zip(before['nodes'],p['nodes']):
            for key in ('id','station_mm','number','route','order','evidence','reasons','source_observation'):
                self.assertEqual(node.get(key),old.get(key))
            self.assertEqual([i['anchor'] for i in node['instances']],[i['anchor'] for i in old['instances']])
        p['version']+=1;self.assertTrue(accepted_plan_current(p))
        p['nodes'][0]['instances'][0]['bubble'][0]+=1;self.assertFalse(accepted_plan_current(p))

    def test_every_generated_object_edits_reopens_and_preserves_original_streams_and_annotation_appearances(self):
        p=self.model()
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'native-review.zip';export_bundle(p,lambda _:SOURCE,target)
            with zipfile.ZipFile(target) as archive:
                manifest=json.loads(archive.read('annotation-manifest.json'));pdf=archive.read('annotated-review.pdf')
                qa=json.loads(archive.read('qa.json'))
            self.assertTrue(qa['source_raw_content_unchanged']);self.assertTrue(qa['original_annotation_appearances_unchanged'])
            self.assertGreater(len(qa['allowed_source_annotation_crossings']),0)
            self.assertLessEqual(len(qa['allowed_source_annotation_crossings']),3)
            names={m['name'] for m in manifest};self.assertEqual(len(names),len(manifest));edited=set()
            with fitz.open(SOURCE) as original,fitz.open(stream=pdf,filetype='pdf') as doc:
                source_appearances=[source_annotation_snapshot(page) for page in original]
                for index,page in enumerate(doc):
                    self.assertEqual(content_hash(page),content_hash(original[index]))
                    self.assertEqual(raw_content_hash(page),raw_content_hash(original[index]))
                    self.assertEqual(source_annotation_snapshot(page)[:len(source_appearances[index])],source_appearances[index])
                    for annotation in page.annots() or []:
                        if annotation.info.get('id') not in names:continue
                        edited.add(annotation.info['id']);annotation.set_info(title='SOFTWARE GRAPHIC ROUNDTRIP')
                        if annotation.type[1]=='FreeText':
                            annotation.set_info(content='SOFTWARE EDIT '+annotation.info.get('content',''))
                            annotation.update(text_color=(.2,.1,.7))
                        else:
                            annotation.set_colors(stroke=(.2,.1,.7));annotation.set_border(width=1.4);annotation.update()
                saved=doc.tobytes(garbage=4,deflate=False)
            self.assertEqual(edited,names)
            for _ in range(2):
                with fitz.open(stream=saved,filetype='pdf') as doc,fitz.open(SOURCE) as original:
                    self.assertEqual({a.info['id'] for page in doc for a in page.annots() or [] if a.info.get('id') in names},names)
                    for index,page in enumerate(doc):
                        self.assertEqual(raw_content_hash(page),raw_content_hash(original[index]))
                        self.assertEqual(source_annotation_snapshot(page)[:len(source_appearances[index])],source_appearances[index])
                        for annotation in page.annots() or []:
                            if annotation.info.get('id') in names:self.assertEqual(annotation.info['title'],'SOFTWARE GRAPHIC ROUNDTRIP')
                    saved=doc.tobytes(garbage=3,deflate=False)

    def test_wrong_registered_source_hash_stops_planning_before_any_graphic_or_model_mutation(self):
        p=self.model();p['sheets'][0]['sha256']='0'*64;before=deepcopy(p)
        with self.assertRaisesRegex(ValueError,'PDF_SOURCE_HASH_MISMATCH'):plan_layout(p,lambda _:SOURCE)
        self.assertEqual(p,before)
