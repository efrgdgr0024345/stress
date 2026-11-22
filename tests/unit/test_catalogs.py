from decimal import Decimal
import unittest
from packages.catalogs import exact_match, map_rows, normalize_record


def row(**changes):
    return {
        "family": "flange",
        "standard": "ASME B16.5",
        "rating": "150",
        "nps": "8",
        "component_type": "WN",
        "facing": "RF",
        "source": "Synthetic test datasheet - not engineering data",
        "quality": "REFERENCE_ONLY",
        "weight_n": "100",
        "studs_weight_n": "40",
        "nut_weight_n": "5",
        "stud_count": "4",
        "weight_scope": "BARE_FLANGE",
        **changes,
    }


class CatalogRules(unittest.TestCase):
    def test_pipe_bore_is_not_silently_used_as_api_flange_bore(self):
        from packages.automation.recognize import specifications
        spec=specifications('FLANGE 10000LB RTJWN 6.615" BORE API 6A TYPE 6BX SIZE 7-1.16','8','flange')
        self.assertEqual(spec['pipe_bore'],'6.615')
        self.assertNotIn('api_bore',spec)
        spec=specifications('API 6A FLANGE API BORE 7-1/16 RTJWN 10000LB','8','flange')
        self.assertEqual(spec['api_bore'],'7 1/16')

    def test_equivalent_explicit_fraction_sizes_match_without_crossing_nps_and_bore_fields(self):
        record=normalize_record(row(standard='API 6A',api_bore='7 1/16'))
        spec={k:record[k] for k in ('family','standard','rating','nps','component_type','facing','api_bore')}
        self.assertEqual(exact_match([record],{**spec,'api_bore':'7.0625'})['status'],'EXACT_MATCH')
        self.assertEqual(exact_match([record],{**spec,'api_bore':'7-1/16'})['status'],'EXACT_MATCH')
        self.assertEqual(exact_match([record],{**spec,'api_bore':'8'})['status'],'NO_EXACT_MATCH')
    def test_half_and_full_bolting_are_explicit(self):
        r = normalize_record(row())
        self.assertEqual(Decimal(r["half_weight_n"]), Decimal("140"))
        self.assertEqual(Decimal(r["full_weight_n"]), Decimal("180"))
        self.assertEqual(len(r["calculations"]), 2)

    def test_no_double_counting_assembly_weight(self):
        r = normalize_record(row(weight_scope="ASSEMBLY_INCLUDES_BOLTING"))
        self.assertIsNone(r["half_weight_n"])
        self.assertIsNone(r["full_weight_n"])

    def test_unknown_values_do_not_become_zero(self):
        r = normalize_record(row(weight_n="N/A", nut_weight_n=None))
        self.assertIsNone(r["weight_n"])
        self.assertIsNone(r["half_weight_n"])
        self.assertEqual(
            normalize_record(row(weight_n="0", weight_scope="UNKNOWN"))["weight_n"], "0"
        )

    def test_api_bore_required_and_not_nps(self):
        with self.assertRaises(ValueError):
            normalize_record(row(standard="API 6A", api_bore=""))
        r = normalize_record(row(standard="API 6A", api_bore="7 1/16"))
        spec = {
            k: r[k]
            for k in ["family", "standard", "rating", "nps", "component_type", "facing"]
        }
        self.assertEqual(exact_match([r], spec)["status"], "INCOMPLETE_SPEC")
        self.assertEqual(
            exact_match([r], {**spec, "api_bore": "8"})["status"], "NO_EXACT_MATCH"
        )
        self.assertEqual(
            exact_match([r], {**spec, "api_bore": "7 1/16"})["status"], "EXACT_MATCH"
        )

    def test_ambiguous_matches_are_never_arbitrarily_selected(self):
        r = normalize_record(row())
        spec = {
            k: r[k]
            for k in ["family", "standard", "rating", "nps", "component_type", "facing"]
        }
        self.assertEqual(
            exact_match([r, {**r, "vendor": "Another vendor"}], spec)["status"],
            "AMBIGUOUS_MATCH",
        )
        self.assertEqual(
            exact_match([r], {**spec, "rating": "300"})["status"], "NO_EXACT_MATCH"
        )

    def test_confirmation_and_numeric_sanity(self):
        for change in [
            {"quality": "MANUFACTURER_CONFIRMED"},
            {"weight_n": "NaN"},
            {"weight_n": "-1"},
            {"stud_count": "2.5"},
            {"half_weight_n": "500"},
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_record(row(**change))

    def test_explicit_mass_and_length_conversion_provenance(self):
        data = row(
            family="valve",
            component_type="BALL",
            end_connection="FLANGED",
            weight_scope="BODY_ONLY",
        )
        fields = list(data) + ["length_mm"]
        values = list(data.values()) + ["2.5"]
        result = map_rows(
            [(7, values)], {k: i for i, k in enumerate(fields)}, {}, "kg", "in", "hash"
        )
        self.assertEqual(result["errors"], [])
        self.assertEqual(Decimal(result["records"][0]["weight_n"]), Decimal("980.665"))
        self.assertEqual(Decimal(result["records"][0]["length_mm"]), Decimal("63.5"))
        self.assertEqual(result["records"][0]["source_row"], 7)
        self.assertEqual(result["units"]["gravity_m_s2"], "9.80665")
