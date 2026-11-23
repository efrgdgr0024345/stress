from decimal import Decimal
import unittest
from packages.engineering.coordinates import coordinate_value


class SourceCoordinateTests(unittest.TestCase):
    def test_signed_cardinal_coordinates_keep_original_fractions(self):
        for text,axis,expected in [('E 3\' 2 1/8"','X','968.375'),('S 2 1/8 in','Y','-53.975'),
                                   ('N -0.5 in','Y','-12.70'),('S -2 in','Y','50.8'),
                                   ('W 100 mm','X','-100'),('EL. +7\' 6"','Z','2286.0')]:
            with self.subTest(text=text):
                parsed=coordinate_value(text)
                self.assertEqual(parsed['axis'],axis);self.assertEqual(Decimal(parsed['value_mm']),Decimal(expected))
                self.assertEqual(parsed['source_text'],text)

    def test_ordinary_axis_dimensions_remain_compatible(self):
        self.assertEqual(Decimal(coordinate_value('-2 1/8 in','X')['value_mm']),Decimal('-53.975'))
        self.assertIsNone(coordinate_value('0 mm','Y')['source_direction'])

    def test_axis_conflicts_missing_units_and_paper_lengths_are_rejected(self):
        for text,axis in [('E 2 in','Y'),('N 42','Y'),('32 px','X'),('UNKNOWN 3 mm','X'),('12 mm',None),('EL NaN mm','Z')]:
            with self.subTest(text=text),self.assertRaises(ValueError):coordinate_value(text,axis)

    def test_printed_iso_fraction_requires_explicit_format_and_retains_source(self):
        for text,axis,expected in [('E 146\'11.5/16"','X','44788.1375'),('S 312\'10.3/8"','Y','-95361.125'),('EL +37\'10.3/4"','Z','11550.65')]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):coordinate_value(text,axis)
                result=coordinate_value(text,axis,'ISO_FT_IN_DOT_FRACTION')
                self.assertEqual(Decimal(result['value_mm']),Decimal(expected));self.assertEqual(result['source_text'],text)
        for text in ['3\'12.1/8"','3\'10.8/8"','3\'10.1/0"','3\'10.3/8','3\'10.5"']:
            with self.subTest(text=text),self.assertRaises(ValueError):coordinate_value(text,'X','ISO_FT_IN_DOT_FRACTION')
