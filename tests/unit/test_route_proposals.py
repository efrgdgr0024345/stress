import unittest
from packages.automation.routes import propose
from packages.automation.recognize import vector_graph
from packages.engineering import renumber,compute_reasons


class RouteProposalTests(unittest.TestCase):
    def graph(self):return {"vertices":[[50,100],[150,100],[250,100],[150,200],[150,300]],"edges":[[0,1],[1,2],[1,3],[3,4]],"page_width":600,"page_height":500}
    def test_main_and_branch_share_tee_and_never_gain_physical_stations(self):
        nodes,issues=propose(self.graph(),0,2,'sheet','LINE-01')
        renumber(nodes);compute_reasons(nodes)
        self.assertEqual([n['number'] for n in nodes],[10,20,30,100,110]);self.assertEqual(issues,[])
        self.assertEqual(nodes[3]['takeoff_id'],nodes[1]['id']);self.assertEqual(nodes[1]['kind'],'tee')
        self.assertTrue(all(n['station_mm'] is None and 'UNVERIFIED_DIMENSION' in n['reasons'] for n in nodes))
        repeated,_=propose(self.graph(),0,2,'sheet','LINE-01');self.assertEqual([n['id'] for n in repeated],[n['id'] for n in nodes])
    def test_loops_and_disconnected_endpoints_are_not_guessed(self):
        graph=self.graph();graph['edges'].append([0,2])
        with self.assertRaisesRegex(ValueError,'loops'):propose(graph,0,2,'sheet','LINE')
        graph=self.graph();graph['vertices'].append([500,400]);graph['edges'].append([4,5]);graph['vertices'].append([550,450])
        with self.assertRaisesRegex(ValueError,'separate'):propose(graph,0,6,'sheet','LINE')
    def test_crossing_strokes_are_not_automatically_a_junction(self):
        graph=vector_graph({'segments':[{'a':[0,0],'b':[50,50]},{'a':[0,50],'b':[50,0]}]})
        self.assertEqual(len(graph['vertices']),4);self.assertEqual(len(graph['edges']),2)
        self.assertFalse(graph['crossings_are_junctions'])
