from evaluator.importing.ut_defaults import defaults
from evaluator.engineering.row_example import calculate,EXAMPLE
import pytest


def test_table_specific_prefill():
    snapshot={'cells':{a:{'value':v} for a,v in {'A133':'JOINT#','B133':'BAND','C133':'DIAM.','H133':'NOM.T','I133':'SCH','C136':'8"','H136':'12.7','I136':'80','A264':'JOINT#','B264':'BAND','C264':'DIAM.','G264':'NOM.T','H264':'SCH','C265':'6"','G265':'10.97','H265':'XS'}.items()}}
    first=defaults(snapshot,'F136','2');second=defaults(snapshot,'E265','E')
    assert first['material']=='A106 B'
    assert first['D_outside_in']=='8.625'
    assert first['nominal_thickness_mm']=='12.7'
    assert first['segment']=='UT section 1'
    assert second['material']=='A234 WPB'
    assert second['D_outside_in']=='6.625'
    assert second['nominal_thickness_mm']=='10.97'
    assert second['segment']=='UT section 2'
    assert 'structural_minimum_mm' not in first
    assert 'P_psi' not in first


def test_each_section_uses_its_own_previous_date():
    first=calculate(EXAMPLE)
    second=calculate(dict(EXAMPLE,previous_date='2024-11-06'))
    assert first['calculated_cr']==pytest.approx(.3/(1169/365))
    assert second['calculated_cr']==pytest.approx(.3/2)
    assert first['calculated_cr']!=second['calculated_cr']
