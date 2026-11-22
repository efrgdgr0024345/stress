"""Independent fixed-field checks against the documented 15.1 interface layout."""
from copy import deepcopy
from decimal import Decimal
import unittest

from packages.automation.recognize import identity
from packages.workbooks.caesar_neutral import assess,neutral_file


def model():
    p={'id':'software-test','title':'SOFTWARE VALIDATION ONLY','line_id':'SOFTWARE-TEST-001','version':1,'nodes':[], 'sheets':[], 'materials':[], 'materials_reviewed':False,'layout_reviewed':False}
    for i in range(2):p['nodes'].append({'id':f'point-{i}','number':10+i*10,'line_id':p['line_id'],'route':'main','order':i,'kind':'endpoint','station_mm':str(i*1000),'evidence':'Synthetic explicit engineering input for software testing only','verification':'reviewed','instances':[]})
    p['nodes'][1]['station_mm']=str((Decimal(1000)**2+Decimal('50.8')**2).sqrt())
    element={'id':identity(p['id'],'point-0','point-1'),'dx_mm':'1000','dy_mm':'0','dz_mm':'-50.8','od_mm':'219.1','wall_mm':'8.18','corrosion_mm':'3','material_code':'106','temperature_c':'80','pressure_mpa':'1.25','elastic_modulus_mpa':'200000','hot_modulus_mpa':'190000','poisson_ratio':'.3','pipe_density_kg_m3':'7850','fluid_density_kg_m3':'0','insulation_thickness_mm':'0','cold_allowable_mpa':'137','hot_allowable_mpa':'125'}
    p['analysis_model']={'local_origin_confirmed':True,'origin_point_id':'point-0','ambient_temperature_c':'20','piping_code_id':3,'vertical_axis':'Z','elements':[element]}
    return p


def sections(data):
    output={};name=None
    for line in data.decode('cp1252').splitlines():
        if line.startswith('#$ '):name=line[3:];output[name]=[]
        else:output[name].append(line)
    return output


def numbers(lines):
    return [Decimal(line[i:i+13]) for line in lines for i in range(2,len(line),13) if line[i:i+13].strip()]


class NeutralTests(unittest.TestCase):
    def test_y_up_target_rotates_canonical_east_north_up_without_reflection(self):
        p=model();p['analysis_model']['vertical_axis']='Y'
        values=numbers(sections(neutral_file(p))['ELEMENTS'][:9])
        self.assertEqual(values[3],-2)
        self.assertEqual(values[4],0)
    def test_fixed_fields_counts_units_and_geometry_follow_official_contract(self):
        p=model();check=assess(p);self.assertTrue(check['available'],check);self.assertFalse(check['qualified_application_roundtrip'])
        s=sections(neutral_file(p));self.assertEqual(len(s['VERSION']),61)
        self.assertEqual(Decimal(s['VERSION'][0][2:15]),15);self.assertEqual(int(s['VERSION'][0][28:36]),1252)
        self.assertTrue(all(len(line)==77 for line in s['VERSION'][1:]))
        self.assertEqual(numbers(s['CONTROL'][:1]),[1,0,0,0,0,0])
        controls=numbers(s['CONTROL'][1:]);self.assertEqual(len(controls),13);self.assertEqual(controls[9],1);self.assertEqual(controls[11],1)
        real=numbers(s['ELEMENTS'][:9]);self.assertEqual(len(real),53);self.assertEqual(real[:2],[10,20])
        self.assertLess(abs(real[2]*Decimal('25.4')-1000),Decimal('.01'))
        self.assertEqual(real[4],-2);self.assertLess(abs(real[5]*Decimal('25.4')-Decimal('219.1')),Decimal('.001'))
        self.assertEqual(real[9],176);self.assertEqual(real[28],Decimal('.3'));self.assertEqual(real[31],0)
        self.assertEqual(numbers(s['ELEMENTS'][12:])[9],1)
        self.assertEqual(len(numbers(s['ALLOWBLS'])),168);self.assertEqual(numbers(s['ALLOWBLS'])[11],3)
        self.assertEqual(numbers(s['MISCEL_1'][:1]),[106])
        units=numbers(s['UNITS'][:4]);self.assertEqual(len(units),22);self.assertEqual(units[7],0)
        self.assertEqual(len(s['UNITS'][4:]),24);self.assertEqual(s['UNITS'][4].strip(),'English')
        self.assertEqual(numbers(s['COORDS'][:1]),[1]);self.assertEqual(numbers(s['COORDS'][1:]),[10,0,0,0])

    def test_missing_geometry_and_unsupported_components_do_not_emit_a_file(self):
        p=model();p['analysis_model']['elements'][0]['dx_mm']=None
        self.assertFalse(assess(p)['available'])
        with self.assertRaises(ValueError):neutral_file(p)
        p=model();p['nodes'][0]['kind']='valve'
        self.assertFalse(assess(p)['available'])
        with self.assertRaises(ValueError):neutral_file(p)

    def test_unaccepted_station_and_changed_origin_are_blocked(self):
        p=model();p['nodes'][0]['verification']='proposed';self.assertFalse(assess(p)['available'])
        p=model();p['analysis_model']['origin_point_id']='previous-revision';self.assertFalse(assess(p)['available'])

    def test_native_text_cannot_inject_a_section(self):
        p=model();p['nodes'][0]['line_id']='LINE\r\n#$ CONTROL';p['nodes'][1]['line_id']=p['nodes'][0]['line_id']
        with self.assertRaises(ValueError):neutral_file(p)

    def test_conflicting_independent_engineering_geometry_is_blocked(self):
        p=model();p['nodes'][1]['station_mm']='500'
        self.assertTrue(any('conflict' in message for message in assess(p)['missing']))
        with self.assertRaises(ValueError):neutral_file(p)

    def test_invalid_properties_and_ambiguous_numbers_do_not_enable_download(self):
        for key,value in [('elastic_modulus_mpa','-1'),('pressure_mpa','-1'),('corrosion_mm','9'),('insulation_density_kg_m3','NaN')]:
            p=model();p['analysis_model']['elements'][0][key]=value
            self.assertFalse(assess(p)['available'],key)
        p=model();p['nodes'][1]['number']=10
        self.assertFalse(assess(p)['available'])
        p=model();p['analysis_model']['ambient_temperature_c']='NaN'
        self.assertFalse(assess(p)['available'])
