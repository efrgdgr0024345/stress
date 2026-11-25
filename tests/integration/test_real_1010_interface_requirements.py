"""Actual-PDF API serialization of evidence-linked, unlocated required interfaces."""
import json
from pathlib import Path
import unittest

from packages.automation.recognize import materials
from services.api import main
from tests.integration import test_api as fixtures

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'fixtures/1010/1010 Reviewed.pdf'
OBSERVATIONS=ROOT/'fixtures/1010/observations/material-delayed-row-page-1.json'


class Real1010InterfaceRequirementApiTests(unittest.TestCase):
    setUp=fixtures.ApiTests.setUp
    tearDown=fixtures.ApiTests.tearDown
    create=fixtures.ApiTests.create
    upload=fixtures.ApiTests.upload

    def test_actual_elbow_requirements_round_trip_as_blue_source_exceptions(self):
        p=self.upload(self.create(),SOURCE.read_bytes())
        observations=json.loads(OBSERVATIONS.read_text())
        sheet=p['sheets'][0]
        self.assertEqual(sheet['sha256'],observations['source_sha256'])
        rows,_,_=materials(observations,sheet,sheet['sha256'])
        p['materials']=[next(m for m in rows if m['item_no']=='3')]
        # Seed retained source observations, not any engineered stations,
        # positions, classifications, acceptance or replacement PDF content.
        with main.db() as connection:
            connection.execute('UPDATE projects SET data=? WHERE id=?',(json.dumps(p),p['id']))
        path=f"/api/v1/projects/{p['id']}/physical-model"
        first=self.client.get(path);self.assertEqual(first.status_code,200,first.text)
        result=first.json()
        self.assertEqual(len(result['components']),2)
        issues=[i for i in result['issues'] if i.get('port')=='theoretical_cod']
        self.assertEqual(len(issues),2)
        self.assertEqual(len({i['requirement_id'] for i in issues}),2)
        for issue in issues:
            self.assertEqual(issue['status'],'REVIEW_REQUIRED');self.assertEqual(issue['color'],'blue')
            self.assertEqual(issue['sheet_id'],sheet['id']);self.assertEqual(issue['source_sha256'],sheet['sha256'])
            self.assertTrue(issue['source_bbox']);self.assertTrue(issue['evidence']);self.assertTrue(issue['source_evidence_id'])
            self.assertIsNone(issue['physical_point_id'])
        self.assertEqual(first.json(),self.client.get(path).json())
        after=self.client.get(f"/api/v1/projects/{p['id']}").json()
        self.assertEqual(after['nodes'],[])
        self.assertEqual(after['materials'][0]['verification'],'proposed')
        self.assertFalse(result['solution']['drawing_pixels_used'])
