"""Graph identity regressions using existing pure rule fixtures only.

These records are isolated software inputs, never physical 1010 source facts,
accepted engineering coordinates, route assignments, or golden approval data.
"""
from copy import deepcopy
import unittest

from packages.engineering import renumber, topology
from packages.engineering.continuations import merge_identity
from packages.engineering.graph_review import renumber_project
from packages.physical.stations import solve_stations
from tests.unit.test_continuations import fixture
from tests.unit.test_engineering import point
from tests.unit.test_station_solver import accept, add


def local_fixture(*point_ids):
    """Give selected fixture points explicitly separate local datum records."""
    p = fixture()
    p['physical_model']['station_constraints'] = []
    for n in p['nodes']:
        n['station_mm'] = None
    for uid in point_ids:
        c = add(p, 'LOCAL_ORIGIN', uid, None, '0')
        n = next(n for n in p['nodes'] if n['id'] == uid)
        sheet = next(s for s in p['sheets'] if s['id'] == n['instances'][0]['sheet_id'])
        c.update(sheet_id=sheet['id'], source_content_hash=deepcopy(sheet['content_hash']))
    accept(p, solve_stations(p))
    return p


class GraphIdentityAuditTests(unittest.TestCase):
    def test_multiline_numbering_is_invariant_to_input_order(self):
        nodes = [point(3, line='B'), point(2, line='A'),
                 point(1, line='B'), point(0, line='A')]
        maps = []
        for ordered in (nodes, list(reversed(nodes)), nodes[1:] + nodes[:1]):
            copy = deepcopy(ordered)
            renumber(copy)
            maps.append({n['id']: n['number'] for n in copy})
        self.assertEqual(maps[0], maps[1])
        self.assertEqual(maps[0], maps[2])
        self.assertEqual(maps[0], {'0': 10, '2': 20, '1': 1000, '3': 1010})

    def test_renumber_only_changes_labels_including_unknown_and_alias_depictions(self):
        p = local_fixture('right')
        # A source role/depiction record is opaque to display numbering.
        p['nodes'][1]['source_feature_links'] = [{'id': 'pure-source-role', 'role': 'boundary'}]
        p['nodes'][1]['source_review_reasons'] = ['PURE_UNRESOLVED_SOURCE_EXCEPTION']
        p['nodes'].append({**point(9), 'route': None, 'order': None,
                           'topology_state': 'UNASSIGNED', 'station_mm': None})
        p['point_aliases'] = {'retired-pure-source-id': 'right'}
        p['nodes'][1]['instances'].append({'sheet_id': 'sheet-extra',
                                          'anchor': [1, 2], 'bubble': [3, 4]})
        before = deepcopy(p)
        mapping = renumber(p['nodes'])
        self.assertEqual({r['point_id'] for r in mapping}, {n['id'] for n in p['nodes']})
        self.assertIn({'point_id': '9', 'old': None, 'new': None}, mapping)
        self.assertIsNone(next(n for n in p['nodes'] if n['id'] == '9')['number'])
        for old, new in zip(before['nodes'], p['nodes']):
            self.assertEqual({k: v for k, v in old.items() if k != 'number'},
                             {k: v for k, v in new.items() if k != 'number'})
        self.assertEqual(p['point_aliases'], before['point_aliases'])
        self.assertEqual(p['physical_model'], before['physical_model'])

    def test_invalid_takeoffs_never_create_a_crossline_or_nonmain_tee_edge(self):
        for invalid in ('crossline', 'nontee', 'branchtee', 'inconsistent'):
            with self.subTest(invalid=invalid):
                main = point(0, kind='tee')
                branch = point(1, route='branch-01')
                branch['takeoff_id'] = main['id']
                nodes = [main, branch]
                if invalid == 'crossline':
                    main['line_id'] = 'OTHER'
                elif invalid == 'nontee':
                    main['kind'] = 'endpoint'
                elif invalid == 'branchtee':
                    main['route'] = 'branch-02'
                else:
                    second = point(2, route='branch-01')
                    second['takeoff_id'] = 'missing-point'
                    nodes.append(second)
                self.assertNotIn((main['id'], branch['id']),
                                 {(e['from'], e['to']) for e in topology(nodes)['edges']})

    def test_equal_values_in_different_local_datums_cannot_merge(self):
        p = local_fixture('left', 'right')
        left, right = p['nodes']
        self.assertEqual(left['station_mm'], right['station_mm'])
        self.assertNotEqual(left['station_proof']['basis_id'], right['station_proof']['basis_id'])
        before = deepcopy(p)
        with self.assertRaisesRegex(ValueError, 'datum|basis'):
            merge_identity(p, 'left', 'right')
        self.assertEqual(p, before)

    def test_matching_local_values_require_fresh_source_not_cached_review_flags(self):
        p = local_fixture('left')
        add(p, 'DELTA', 'left', 'right', '0')
        accept(p, solve_stations(p))
        left, right = p['nodes']
        self.assertEqual(left['station_proof']['basis_id'], right['station_proof']['basis_id'])
        self.assertFalse(right.get('station_review_reasons'))
        right['instances'][0]['anchor'] = [51, 50]
        before = deepcopy(p)
        with self.assertRaisesRegex(ValueError, 'datum|basis|stale'):
            merge_identity(p, 'left', 'right')
        self.assertEqual(p, before)

    def test_merge_retains_local_proof_history_and_original_source_stamps(self):
        p = local_fixture('right')
        old = p['nodes'][1]
        old['manual_station_basis'] = {'basis': 'LOCAL_ORIGIN',
                                       'basis_id': old['station_proof']['basis_id']}
        old['station_proof_history'] = [{'pure_rule_record': 'prior-source-proof'}]
        old['station_history'] = [{'pure_rule_record': 'prior-review-event'}]
        proof = deepcopy(old['station_proof'])
        original_stamps = deepcopy(p['physical_model']['station_constraints'][0]['source_point_stamps'])
        kept = merge_identity(p, 'left', 'right')
        self.assertEqual(kept['id'], 'left')
        self.assertEqual(kept['station_mm'], '0')
        self.assertEqual(kept['station_proof'], proof)
        self.assertEqual(kept['manual_station_basis'], old['manual_station_basis'])
        self.assertEqual(kept['station_proof_history'], old['station_proof_history'])
        self.assertEqual(kept['station_history'], old['station_history'])
        self.assertEqual(p['point_aliases']['right'], 'left')
        self.assertEqual({i['sheet_id'] for i in kept['instances']}, {'sheet-a', 'sheet-b'})
        c = p['physical_model']['station_constraints'][0]
        self.assertEqual(c['from_point_id'], 'left')
        self.assertEqual(c['source_point_stamps'], original_stamps)
        self.assertEqual(c['source_point_stamps'][0]['point_id'], 'right')
        solution = solve_stations(p)
        row = solution['points'][0]
        self.assertEqual(row['basis'], 'LOCAL_ORIGIN')
        self.assertIsNone(row['absolute_station_mm'])
        self.assertEqual(row['existing_station_mm'], '0')
        self.assertIn('STATION_SOLUTION_STALE', {i['code'] for i in solution['issues']})

    def test_number_history_keeps_retired_label_and_unassigned_null(self):
        p = fixture()
        p['nodes'].append({**point(9, line='LINE-A'), 'route': None, 'order': None,
                           'topology_state': 'UNASSIGNED', 'station_mm': None})
        renumber_project(p, 'pure-rule-before-merge')
        retired_number = p['nodes'][1]['number']
        merge_identity(p, 'left', 'right')
        renumber_project(p, 'pure-rule-after-merge')
        record = p['numbering_history'][-1]
        self.assertIn({'point_id': '9', 'old': None, 'new': None}, record['mapping'])
        self.assertIn({'retired_point_id': 'right', 'physical_point_id': 'left',
                       'old': retired_number, 'new': 10}, record['alias_rows'])
        meaningful_map = deepcopy(p['numbering_map'])
        history_count = len(p['numbering_history'])
        p['nodes'][0]['instances'][0]['bubble'] = [123, 234]
        renumber_project(p, 'pure-rule-display-only-save')
        self.assertEqual(p['numbering_map'], meaningful_map)
        self.assertEqual(len(p['numbering_history']), history_count)
