"""Independent published-offset decoding; SOFTWARE-ONLY vectors, never 1010 data.

Offsets/counts below come from the official 15.1 contract documented in
docs/CII_151_COMPONENT_CONTRACT.md. No writer formatting, field-list, ordering,
section, or numeric parsing helpers are used to construct the expectations.
This verifies candidate structure; it is not a CAESAR application round trip.
"""
from copy import deepcopy
from decimal import Decimal
import unittest

from packages.workbooks.caesar_neutral import assess, neutral_file
from packages.workbooks.cii_components import native_component_plan, save_record
from tests.unit.test_cii_components import (
    EVIDENCE, REVIEWER, WHEN, add_reviewed_records, software_model,
)


def decode_sections(test, encoded):
    test.assertIsInstance(encoded, bytes)
    test.assertTrue(encoded.endswith(b'\r\n'))
    test.assertNotIn(b'\n', encoded.replace(b'\r\n', b''))
    output = {}
    current = None
    for raw in encoded[:-2].split(b'\r\n'):
        line = raw.decode('cp1252')
        if line.startswith('#$ '):
            current = line[3:]
            test.assertNotIn(current, output, 'Duplicate section header')
            output[current] = []
        else:
            test.assertIsNotNone(current, 'Data before first section header')
            output[current].append(line)
    return output


def fixed_numbers(test, line, count, integers=False):
    test.assertEqual(line[:2], '  ')
    test.assertEqual(len(line), 2 + 13 * count)
    values = []
    for offset in range(count):
        field = line[2 + 13 * offset:15 + 13 * offset]
        test.assertTrue(field.strip(), 'Unexpected blank required numeric slot')
        value = Decimal(field)
        test.assertTrue(value.is_finite())
        if integers:
            test.assertEqual(value, value.to_integral_value())
        values.append(value)
    return values


def fixed_text(test, line, maximum=100):
    test.assertEqual(line[:7], ' ' * 7)
    test.assertEqual(line[12], ' ')
    length = int(line[7:12])
    test.assertGreaterEqual(length, 0)
    test.assertLessEqual(length, maximum)
    payload = line[13:]
    test.assertGreaterEqual(len(payload), length)
    test.assertTrue(not payload[length:] or not payload[length:].strip())
    return payload[:length]


def decode_control(test, sections):
    lines = sections['CONTROL']
    test.assertEqual(len(lines), 4)
    return sum((fixed_numbers(test, line, count, integers=True)
                for line, count in zip(lines, (6, 6, 6, 1))), [])


def decode_elements(test, sections):
    lines = sections['ELEMENTS']
    test.assertEqual(len(lines) % 15, 0)
    output = {}
    for offset in range(0, len(lines), 15):
        block = lines[offset:offset + 15]
        real = sum((fixed_numbers(test, line, count)
                    for line, count in zip(block[:9], (6,) * 8 + (5,))), [])
        fixed_text(test, block[9], maximum=500)
        fixed_text(test, block[10], maximum=500)
        fixed_numbers(test, block[11], 2)
        pointers = sum((fixed_numbers(test, line, count, integers=True)
                        for line, count in zip(block[12:15], (6, 6, 3))), [])
        key = (int(real[0]), int(real[1]))
        test.assertNotIn(key, output)
        output[key] = {'real': real, 'pointers': pointers}
    return output


class CiiComponentContractTests(unittest.TestCase):
    def test_control_and_element_pointers_select_exact_auxiliary_blocks(self):
        p = software_model()
        check = assess(p)
        self.assertTrue(check['available'], check)
        self.assertFalse(check['qualified_application_roundtrip'])
        self.assertEqual(check['status'], 'IMPORT_CANDIDATE_ONLY')
        sections = decode_sections(self, neutral_file(p))
        # Six first-record counts, then thirteen published control positions.
        self.assertEqual(decode_control(self, sections),
                         [3, 0, 0, 0, 0, 0,
                          0, 1, 0, 1, 0, 0, 0, 0, 0, 3, 1, 1, 0])
        expected = {(10, 20): (0, 0, 1, 1),
                    (20, 30): (1, 0, 0, 2),
                    (20, 100): (0, 1, 0, 3)}
        elements = decode_elements(self, sections)
        self.assertEqual(set(elements), set(expected))
        for pair, (rigid, restraint, tee, allowable) in expected.items():
            pointers = elements[pair]['pointers']
            self.assertEqual(len(pointers), 15)
            # Published 1-based IEL positions 2, 4, 11 and 10 respectively.
            self.assertEqual((pointers[1], pointers[3], pointers[10], pointers[9]),
                             (rigid, restraint, tee, allowable))
            self.assertTrue(all(value == 0 for position, value in enumerate(pointers)
                                if position not in (1, 3, 9, 10)))
        self.assertEqual(sections['BEND'], [])
        self.assertEqual(len(sections['RIGID']), 1)
        # 444.82216152605 N / 4.4482216152605 = 100 lbf; second field is type 1.
        self.assertEqual(fixed_numbers(self, sections['RIGID'][0], 2), [100, 1])

    def test_restraint_has_six_four_line_slots_and_force_per_length_units(self):
        sections = decode_sections(self, neutral_file(software_model()))
        rows = sections['RESTRANT']
        self.assertEqual(len(rows), 24)
        for slot in range(6):
            first, second, tag, guid = rows[slot * 4:slot * 4 + 4]
            values = fixed_numbers(self, first, 6) + fixed_numbers(self, second, 3)
            if slot == 0:
                self.assertEqual(values[:2], [100, 14])
                expected_stiffness = Decimal(1000) * Decimal('25.4') / Decimal('4.4482216152605')
                self.assertLess(abs(values[2] - expected_stiffness), Decimal('.001'))
                # Gap 25.4 mm = 1 in. Mu is dimensionless; ground/CNode and
                # unskewed target-axis cosine slots are explicitly zero here.
                self.assertEqual(values[3:], [1, Decimal('.2'), 0, 0, 0, 0])
                self.assertEqual(fixed_text(self, tag), 'SOFTWARE SUPPORT')
                self.assertEqual(fixed_text(self, guid), 'SOFTWARE-GUID')
            else:
                self.assertEqual(values, [0] * 9)
                self.assertEqual(fixed_text(self, tag), '')
                self.assertEqual(fixed_text(self, guid), '')

    def test_tee_has_two_exact_42_value_slots_with_published_sif_offsets(self):
        sections = decode_sections(self, neutral_file(software_model()))
        rows = sections['SIF&TEES']
        self.assertEqual(len(rows), 14)
        actual = sum((fixed_numbers(self, line, 6) for line in rows), [])
        expected = [Decimal(0)] * 84
        # Literal 1-based positions transcribed from the official field list,
        # independently of the writer's field constants or component plan.
        expected_values = {1: '20', 2: '3', 3: '1.25', 4: '1.5',
                           13: '1.4', 14: '1.6', 15: '1.1', 16: '1.2',
                           17: '1.3', 18: '1.9', 23: '9999.99', 24: '0',
                           25: '1.7', 26: '1.8',
                           65: '9999.99', 66: '9999.99'}
        for position, value in expected_values.items():
            expected[position - 1] = Decimal(value)
        self.assertEqual(actual, expected)
        # Geometric overrides and a second physical tee were not supplied.
        self.assertEqual(actual[4:12], [0] * 8)
        self.assertEqual(actual[42], 0)

    def test_explicit_target_axis_restraint_is_not_rotated_with_canonical_geometry(self):
        p = software_model(with_records=False)
        p['analysis_model']['vertical_axis'] = 'Y'
        add_reviewed_records(p)
        sections = decode_sections(self, neutral_file(p))
        branch = decode_elements(self, sections)[(20, 100)]['real']
        self.assertEqual(branch[2:4], [0, 0])
        self.assertLess(abs(branch[4] + Decimal(500) / Decimal('25.4')), Decimal('.00001'))
        restraint = fixed_numbers(self, sections['RESTRANT'][0], 6)
        self.assertEqual(restraint[:2], [100, 14])

    def test_bend_cannot_be_enabled_by_review_checkbox_or_unverified_reference_strings(self):
        p = software_model()
        before = deepcopy(p['nodes'])
        save_record(p, {'kind': 'BEND', 'component_id': None, 'point_id': 'c',
                        'element_id': None, 'source_sheet_id': 'SOFTWARE-ONLY-SHEET',
                        'review_state': 'REVIEWED', 'evidence': EVIDENCE,
                        'values': {'radius_mm': '100', 'native_to_point_id': 'c',
                                   'representation_note': EVIDENCE,
                                   'vendor_geometry_reference': 'SOFTWARE ONLY: no verified vendor sample',
                                   'vendor_field_layout_reference': 'SOFTWARE ONLY: unresolved field count'}},
                    REVIEWER, WHEN)
        codes = {i['code'] for i in native_component_plan(p)['issues']}
        self.assertTrue({'BEND_NATIVE_GEOMETRY_CONTRACT_UNVERIFIED',
                         'BEND_NEUTRAL_FIELD_LAYOUT_AMBIGUOUS'} <= codes)
        self.assertFalse(assess(p)['available'])
        with self.assertRaisesRegex(ValueError, 'BEND'):
            neutral_file(p)
        self.assertEqual(p['nodes'], before)
