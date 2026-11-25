"""Actual reviewed-PDF OCR rows: requirement coverage, not original golden counts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from packages.automation.recognize import materials
from packages.physical import audit,prepare,requirements
from tests.unit.test_physical_model import project,node,mapped

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'fixtures/1010/1010 Reviewed.pdf'
OBSERVATIONS=ROOT/'fixtures/1010/observations/material-delayed-row-page-1.json'
SHA='7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59'


class Real1010RequirementTests(unittest.TestCase):
    def source(self):
        observed=json.loads(OBSERVATIONS.read_text())
        self.assertEqual(observed['source_sha256'],SHA)
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),SHA)
        p=project();sheet=p['sheets'][0]
        sheet.update(sha256=SHA,page_index=0,width=observed['width'],height=observed['height'])
        return observed,p,sheet

    def pv(self):
        observed,p,sheet=self.source()
        observation=json.loads((ROOT/'fixtures/1010/observations/process-tag-pv-7680-page-2.json').read_text())
        self.assertEqual(observation['source_sha256'],SHA)
        material=deepcopy(observation['material_observation'])
        sheet.update(id=material['sheet_id'],page_index=observation['page_index'])
        p['materials']=[material]
        return p,material

    def test_actual_delayed_elbow_count_repairs_all_metadata_without_human_approval(self):
        observed,p,sheet=self.source()
        rows,issues,_=materials(observed,sheet,SHA)
        elbow=next(m for m in rows if m['item_no']=='3')
        self.assertEqual(elbow['family'],'elbow')
        self.assertEqual(elbow['quantity_raw'],'2');self.assertEqual(elbow['quantity'],2)
        self.assertEqual(elbow['quantity_unit'],'count');self.assertEqual(elbow['quantity_value'],'2')
        self.assertEqual(elbow['verification'],'proposed')
        self.assertEqual(elbow['source_sha256'],SHA)
        self.assertTrue(elbow['word_evidence_ids'])
        p['materials']=[elbow]
        components,_,_=requirements(p)
        self.assertEqual(len(components),2)
        self.assertEqual([list(c['ports']) for c in components],[['theoretical_cod'],['theoretical_cod']])
        self.assertTrue(all(c['verification']=='proposed' for c in components))
        prepare(p);result=audit(p)
        ports=[i for i in result['issues'] if i.get('port')=='theoretical_cod']
        self.assertEqual(len(ports),2)
        self.assertEqual(len({i['requirement_id'] for i in ports}),2)
        self.assertTrue(all(i['code']=='UNCONFIRMED_ELBOW_COD' and i['color']=='blue' and i['status']=='REVIEW_REQUIRED' for i in ports))
        self.assertTrue(all(i['source_sha256']==SHA and i['source_bbox']==elbow['source_bbox'] and i['evidence'] for i in ports))
        self.assertTrue(all(i['physical_point_id'] is None for i in ports))
        self.assertEqual(p['nodes'],[])
        self.assertEqual([i['id'] for i in ports],[i['id'] for i in audit(p)['issues'] if i.get('port')=='theoretical_cod'])

    def test_low_confidence_quantity_observation_remains_unresolved(self):
        observed,p,sheet=self.source()
        for w in observed['words']:
            if w['text']=='2' and w['bbox'][0]>2450:w['confidence']=.2
        rows,_,_=materials(observed,sheet,SHA)
        p['materials']=[next(m for m in rows if m['item_no']=='3')]
        self.assertIsNone(p['materials'][0]['quantity'])
        self.assertEqual(p['materials'][0]['quantity_unit'],'unresolved')
        self.assertEqual(requirements(p)[0],[])
        issue=next(i for i in audit(p)['issues'] if i['code']=='COMPONENT_QUANTITY_UNRESOLVED')
        self.assertEqual(issue['color'],'blue');self.assertEqual(issue['source_sha256'],SHA)
        self.assertEqual(p['nodes'],[])

    def test_delayed_row_repair_never_turns_a_pipe_length_into_component_count(self):
        observed,p,sheet=self.source()
        # A deliberately changed classification is a negative rule input, not
        # a claim that the real elbow row is a pipe or a new golden fixture.
        for w in observed['words']:
            if w['text']=='ELBOW':w['text']='PIPE'
        rows,_,_=materials(observed,sheet,SHA)
        pipe=next(m for m in rows if m['item_no']=='3')
        self.assertEqual(pipe['family'],'pipe');self.assertEqual(pipe['quantity_raw'],'2')
        self.assertIsNone(pipe['quantity']);self.assertEqual(pipe['quantity_unit'],'unresolved')

    def test_stale_interface_and_unknown_station_have_distinct_stable_port_checks(self):
        observed,p,sheet=self.source();rows,_,_=materials(observed,sheet,SHA)
        elbow=next(m for m in rows if m['item_no']=='3')
        p['materials']=[elbow];p['nodes']=[node('unproved-cod',None,kind='elbow')]
        components=prepare(p)['components'];mapped(p,components[0],['unproved-cod'])
        components[0]['ports']['theoretical_cod']['proof']['content_hash']=['older-source-hash']
        first=audit(p)['issues'];second=audit(p)['issues']
        self.assertEqual([i['id'] for i in first],[i['id'] for i in second])
        self.assertEqual(len({i['id'] for i in first}),len(first))
        checks={i['check'] for i in first if i['component_id']==components[0]['id']}
        self.assertTrue({'SOURCE_ASSOCIATION_UNPROVED','STATION_UNPROVED'}<=checks)
        self.assertTrue(all(i['port']=='theoretical_cod' and i['color']=='blue' for i in first))
        self.assertIsNone(p['nodes'][0]['station_mm'])

    def test_tag_only_process_component_requires_classification_instead_of_silent_omission(self):
        p,material=self.pv()
        result=audit(p)
        self.assertEqual(result['components'],[])
        self.assertEqual(len(result['issues']),1)
        issue=result['issues'][0]
        self.assertEqual(issue['code'],'COMPONENT_CLASSIFICATION_REQUIRED')
        self.assertEqual(issue['color'],'blue');self.assertEqual(issue['source_sha256'],SHA)
        self.assertIsNone(issue['physical_point_id']);self.assertIsNone(issue['port'])
        self.assertEqual(p['nodes'],[])

    def test_source_bound_two_end_profile_retains_both_ports_without_classifying_the_component(self):
        p,material=self.pv()
        material['connection_profile']={'kind':'TWO_PROCESS_ENDS_CLASSIFICATION_UNCONFIRMED','source_sha256':SHA,
            'evidence':'Source inventory observes two process ends for PV-7680; valve/instrument type is not proved.'}
        prepare(p);result=audit(p)
        self.assertEqual(len(result['components']),1)
        component=result['components'][0]
        self.assertEqual(component['kind'],'inline_component_unclassified')
        self.assertEqual(component['family'],'other');self.assertEqual(component['verification'],'proposed')
        self.assertEqual(set(component['ports']),{'process_in','process_out'})
        self.assertTrue(all(v is None for v in component['ports'].values()))
        self.assertEqual({i['port'] for i in result['issues'] if i['component_id']==component['id']},{'process_in','process_out'})
        self.assertTrue(all(i['code']=='COMPONENT_CLASSIFICATION_REQUIRED' and i['color']=='blue' for i in result['issues']))
        self.assertEqual(p['nodes'],[])
        # Source identity changes never preserve the evidence-derived port count.
        p['sheets'][0]['sha256']='f'*64
        self.assertEqual(requirements(p)[0],[])
        prepare(p);self.assertTrue(p['physical_model']['retired_components'])

    def test_incomplete_or_wrong_source_connection_profile_does_not_infer_ports(self):
        for change in ({'source_sha256':'f'*64},{'evidence':''},{'kind':'ASSUMED_FROM_TAG'}):
            p,material=self.pv()
            material['connection_profile']={'kind':'TWO_PROCESS_ENDS_CLASSIFICATION_UNCONFIRMED','source_sha256':SHA,
                'evidence':'Source observations show two physical process ends, component classification unknown.',**change}
            self.assertEqual(requirements(p)[0],[])
            self.assertIn('COMPONENT_CLASSIFICATION_REQUIRED',{i['code'] for i in audit(p)['issues']})

    def test_classification_stays_blue_after_independent_port_and_station_review(self):
        p,material=self.pv()
        material['connection_profile']={'kind':'TWO_PROCESS_ENDS_CLASSIFICATION_UNCONFIRMED','source_sha256':SHA,
            'evidence':'Source observations show two process ends; physical component family remains unproved.'}
        # Explicit unit-rule inputs only: these accepted stations and point
        # tokens are not real 1010 evidence or an engineered source model.
        p['nodes']=[node('rule-in','0'),node('rule-out','100',order=1)]
        for n in p['nodes']:n['instances'][0]['sheet_id']=material['sheet_id']
        component=prepare(p)['components'][0]
        mapped(p,component,['rule-in','rule-out'])
        for value in component['ports'].values():value['proof']['sheet_id']=material['sheet_id']
        result=audit(p)
        unclassified=[i for i in result['issues'] if i['check']=='COMPONENT_CLASSIFICATION_UNPROVED']
        self.assertEqual({i['physical_point_id'] for i in unclassified},{'rule-in','rule-out'})
        self.assertEqual({i['port'] for i in unclassified},{'process_in','process_out'})
        self.assertTrue(all(i['code']=='COMPONENT_CLASSIFICATION_REQUIRED' and i['color']=='blue' for i in unclassified))
