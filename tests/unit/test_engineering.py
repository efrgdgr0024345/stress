from copy import deepcopy
from decimal import Decimal
import unittest
from packages.engineering import dimension_mm, renumber, compute_reasons, topology


def point(i, line="A", route="main", station=None, kind="endpoint"):
    return {
        "id": str(i),
        "line_id": line,
        "route": route,
        "order": i,
        "kind": kind,
        "number": None,
        "station_mm": station,
        "evidence": "Source dimension" if station is not None else "",
        "instances": [{"sheet_id": "sheet-a", "anchor": [10, 20], "bubble": [40, 50]}],
    }


class EngineeringTests(unittest.TestCase):
    def test_exact_mixed_units(self):
        for text, expected in [
            ("6 in", "152.4"),
            ("2 1/8 in", "53.975"),
            ("0.5 in", "12.70"),
            ("3' 2\"", "965.2"),
            ("3' 2 in", "965.2"),
            ("-1/2 in", "-12.7"),
            ("152.4 mm", "152.4"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(dimension_mm(text), Decimal(expected))

    def test_no_inferred_or_invalid_units(self):
        for text in [
            "1200",
            "nan mm",
            "1/0 in",
            "unknown",
            "4 px",
            "mm",
            "in",
            "1 2 in",
            "--2 in",
            "1-2 in",
        ]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                dimension_mm(text)

    def test_main_then_nonoverlapping_long_branches(self):
        nodes = [point(i) for i in range(33)]
        nodes += [point(i + 100, route="branch-01") for i in range(16)]
        nodes += [point(200, route="branch-02")]
        renumber(nodes)
        self.assertEqual(nodes[32]["number"], 330)
        self.assertEqual(nodes[33]["number"], 400)
        self.assertEqual(nodes[-2]["number"], 550)
        self.assertEqual(nodes[-1]["number"], 600)
        self.assertEqual(len({n["number"] for n in nodes}), len(nodes))

    def test_new_line_uses_maximum_including_branches(self):
        nodes = (
            [point(1)]
            + [point(i + 2, route="branch-01") for i in range(126)]
            + [point(999, line="B")]
        )
        renumber(nodes)
        self.assertEqual(nodes[-2]["number"], 1350)
        self.assertEqual(nodes[-1]["number"], 2000)

    def test_continuation_and_manual_geometry_survive_numbering(self):
        nodes = [point(1), point(2)]
        nodes[0]["instances"].append(
            {"sheet_id": "sheet-b", "anchor": [80, 90], "bubble": [70, 60]}
        )
        before = deepcopy(nodes)
        renumber(nodes)
        for a, b in zip(nodes, before):
            self.assertEqual(a["instances"], b["instances"])
            self.assertEqual(a["station_mm"], b["station_mm"])
        self.assertEqual(len(nodes), 2)
        self.assertEqual(len(nodes[0]["instances"]), 2)

    def test_six_inch_rule_inclusive_and_physical(self):
        for gap, blue in [("50.8", True), ("152.4", True), ("152.4001", False)]:
            nodes = [
                point(1, station="0", kind="support"),
                point(2, station=gap, kind="support"),
            ]
            compute_reasons(nodes)
            self.assertEqual(nodes[0]["reasons"], [])
            self.assertEqual("SUPPORT_WITHIN_6_IN" in nodes[1]["reasons"], blue)

    def test_unverified_support_not_scaled_from_pixels(self):
        nodes = [point(1, station="0", kind="support"), point(2, kind="support")]
        compute_reasons(nodes)
        self.assertEqual(nodes[1]["reasons"], ["UNVERIFIED_DIMENSION"])

    def test_flags_survive_renumber_and_ignore_other_route(self):
        nodes = [
            point(1, station="0", kind="support"),
            point(2, station="50.8", kind="support"),
            point(3, route="branch-01", station="51", kind="support"),
        ]
        compute_reasons(nodes)
        reasons = deepcopy([n["reasons"] for n in nodes])
        renumber(nodes)
        compute_reasons(nodes)
        self.assertEqual([n["reasons"] for n in nodes], reasons)
        self.assertEqual(nodes[2]["reasons"], [])

    def test_shuffled_sheet_instances_do_not_set_route_order(self):
        nodes = [point(2), point(0), point(1)]
        renumber(nodes)
        self.assertEqual([n["number"] for n in nodes], [30, 10, 20])

    def test_branch_without_main_is_not_numbered(self):
        with self.assertRaises(ValueError):
            renumber([point(1, route="branch-01")])

    def test_branch_order_by_takeoff_and_shared_tee_graph(self):
        nodes = [
            point(0, kind="tee"),
            point(1, kind="tee"),
            point(2, route="branch-01"),
            point(3, route="branch-02"),
        ]
        nodes[2]["takeoff_id"] = "1"
        nodes[3]["takeoff_id"] = "0"
        renumber(nodes)
        self.assertEqual(nodes[3]["number"], 100)
        self.assertEqual(nodes[2]["number"], 200)
        graph = topology(nodes)
        self.assertEqual(len(graph["points"]), 4)
        self.assertIn(
            {"from": "0", "to": "3", "line_id": "A", "route": "branch-02"},
            graph["edges"],
        )
