"""Recognition locations stay separate from accepted engineering geometry."""
from copy import deepcopy
from pathlib import Path
import math
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from packages.automation.extract import extract_page
from packages.automation.contracts import PageEvidence, Symbol
from packages.automation.recognize import node_proposals
from packages.automation.symbols import flange_symbols

SOURCE=Path(__file__).resolve().parents[2]/'fixtures/1010/1010 Reviewed.pdf'
SHA='7b97d44bef3d544c4c98ed0667c29607ce58fa4a401dd2463f66010a9615bb59'


def drawing(points,kind='s',width=.25):
    xs,ys=zip(*points)
    return {'type':kind,'width':width,'fill':(0,0,0) if kind=='fs' else None,
            'rect':(min(xs),min(ys),max(xs),max(ys)), 'closePath':True,
            'items':[('l',a,b) for a,b in zip(points,points[1:]+points[:1])]}


def paths():
    return [drawing([(70,90),(73,90),(73,110),(70,110)]),
            drawing([(86,98),(90,96),(94,98),(94,102),(90,104),(86,102)],'fs'),
            {'type':'s','width':1.5,'items':[('l',(90,100),(160,100))],'rect':(90,100,160,100)}]


class SymbolTests(unittest.TestCase):
    def test_separate_face_and_dot_with_stable_source_identity(self):
        proposals,limited=flange_symbols(paths(),SHA,0)
        self.assertFalse(limited);self.assertEqual(len(proposals),1)
        item=Symbol.model_validate(proposals[0])
        self.assertEqual(item.flange_face,(70,100));self.assertEqual(item.opposite_pipe_dot,(90,100))
        self.assertEqual(proposals,flange_symbols(paths(),SHA,0)[0])
        self.assertNotEqual(item.id,flange_symbols(paths(),'1'*64,0)[0][0]['id'])
        self.assertNotIn('station_mm',proposals[0]);self.assertNotIn('route',proposals[0])

    def test_missing_conflicting_and_ambiguous_evidence_stays_unknown(self):
        source=paths()
        for subset in (source[:1],source[:2],source[1:]):
            self.assertEqual(flange_symbols(subset,SHA,0)[0],[])
        source[2]['items']=[('l',(90,100),(90,160))]
        self.assertEqual(flange_symbols(source,SHA,0)[0],[])
        source=paths();second=deepcopy(source[1])
        second['items']=[(k,(a[0]+2,a[1]),(b[0]+2,b[1])) for k,a,b in second['items']]
        second['rect']=(88,96,96,104);source.append(second)
        self.assertEqual(flange_symbols(source,SHA,0)[0],[])
        source=paths();source[1]['fill']=(1,0,0)
        self.assertEqual(flange_symbols(source,SHA,0)[0],[])

    def test_rotation_and_scale_do_not_turn_page_geometry_into_physical_units(self):
        for scale in (.5,1,1.5):
            source=paths()
            transform=lambda p:(300-scale*p[1],30+scale*p[0])
            for path in source:
                path['items']=[(k,transform(a),transform(b)) for k,a,b in path['items']]
                points=[p for _,a,b in path['items'] for p in (a,b)]
                xs,ys=zip(*points);path['rect']=(min(xs),min(ys),max(xs),max(ys));path['width']*=scale
            found,limited=flange_symbols(source,SHA,0)
            self.assertEqual(len(found),1);self.assertFalse(limited)
            self.assertEqual(found[0]['flange_face'],list(transform((70,100))))
            self.assertEqual(found[0]['opposite_pipe_dot'],list(transform((90,100))))

    def test_resource_bound_and_untrusted_geometry_contract(self):
        with patch('packages.automation.symbols.MAX_MATCH_WORK',0):
            self.assertEqual(flange_symbols(paths(),SHA,0),([],True))
        item=flange_symbols(paths(),SHA,0)[0][0]
        for changes in ({'flange_face':item['opposite_pipe_dot']},{'flange_face':[1000,1000]},
                        {'source_paths':[50000,1]},{'station_mm':0}):
            with self.assertRaises(ValidationError):Symbol.model_validate({**item,**changes})

    def test_real_source_locates_thirteen_visible_flange_symbols_without_a_fake_model(self):
        all_ids=set()
        for index,count in ((0,4),(1,9)):
            evidence=extract_page(SOURCE,index,ocr=False)
            validated=PageEvidence.model_validate({**evidence,'isolation':'bounded-pilot'})
            self.assertEqual(len(validated.symbols),count)
            self.assertEqual(evidence['source_sha256'],SHA)
            old={k:v for k,v in evidence.items() if k!='symbols'}
            self.assertEqual(PageEvidence.model_validate({**old,'isolation':'provider-function'}).symbols,[])
            if index==0:
                invalid=deepcopy(evidence);invalid['symbols'][0]['bbox'][0]=-1
                with self.assertRaises(ValidationError):PageEvidence.model_validate({**invalid,'isolation':'provider-function'})
            for symbol in validated.symbols:
                self.assertNotIn(symbol.id,all_ids);all_ids.add(symbol.id)
                self.assertGreater(math.dist(symbol.flange_face,symbol.opposite_pipe_dot),10)
            sheet={'id':f'sheet-{index}','page_index':index,'line_id':'source-line',
                   'width':evidence['width'],'height':evidence['height']}
            nodes,_=node_proposals(evidence,sheet,SHA)
            self.assertEqual(nodes,[]) # Graphical location does not establish a physical route or station.
        first=extract_page(SOURCE,0,ocr=False)['symbols'][0]
        self.assertAlmostEqual(first['opposite_pipe_dot'][0],896.865,places=2)
        self.assertAlmostEqual(first['flange_face'][0],881.993,places=2)

