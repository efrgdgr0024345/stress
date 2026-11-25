"""Exact supplied PDF schedules keep unavailable values explicit and separate."""
import unittest
from packages.catalogs import schedule_lines
from packages.engineering import validate
from tests.unit import test_source_exceptions as source_fixture


class RealScheduleTests(unittest.TestCase):
    def test_every_real_flange_keeps_all_three_weight_labels_with_na_values(self):
        p=source_fixture.SourceExceptionTests().model();validate(p)
        for page,expected in ((0,2),(1,4)):
            sheet=p['sheets'][page]
            materials=[m for m in p['materials'] if m['sheet_id']==sheet['id'] and m['family'] in ('flange','valve')]
            self.assertEqual(len(materials),expected)
            lines=schedule_lines(materials)
            for m in materials:
                entries=[line for line in lines if line.startswith(m['item_no']+'  ')]
                self.assertEqual(len(entries),1)
                self.assertIn('W_flange: N/A N' if m['family']=='flange' else 'W_valve: N/A N',entries[0])
            flange_count=sum(m['family']=='flange' for m in materials)
            self.assertEqual(sum('W_half: N/A N | W_full: N/A N' in line for line in lines),flange_count)
            self.assertEqual(lines.count('PROJECT MANUFACTURER: UNCONFIRMED'),len(materials))
            self.assertTrue(all('W_flange: 0' not in line and 'W_valve: 0' not in line for line in lines))
        self.assertEqual(sum(m['quantity'] for m in p['materials'] if m['family']=='flange'),13)
        self.assertEqual(sum(m['quantity'] for m in p['materials'] if m['family']=='valve'),5)
