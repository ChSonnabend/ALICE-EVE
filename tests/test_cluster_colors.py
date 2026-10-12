import math
import pytest
from alice_renderer.model import color_value,capabilities,RenderSettings
from alice_renderer.cluster_colors import CLUSTER_COLOR_FIELDS
from alice_renderer.scene_config import recipe,resolve_settings


def test_measured_quantities_and_signed_normalized_residuals():
    c={'detector':'TPC','tpc_profile':{'sigma_pad':2.,'sigma_time_bins':3.},
       'measurements':{'q_tot':120.,'q_max':30.,'error_y_cm':.2,'error_z_cm':.4,'residual_y_cm':-.3,'residual_z_cm':.8}}
    expected=[2,3,120,30,4,.2,.4,-.3,.8,-1.5,2]
    for mode,v in zip(CLUSTER_COLOR_FIELDS,expected):
        assert color_value(c,mode)==pytest.approx(v)
        assert mode in capabilities([c])
        assert resolve_settings(recipe(RenderSettings(cluster_color_mode=mode)),'unused.json').cluster_color_mode==mode


def test_missing_invalid_and_zero_denominators_are_not_colors():
    c={'detector':'TPC','tpc_profile':{'sigma_pad':2.,'sigma_time_bins':3.},'measurements':{'q_tot':5,'q_max':0,'residual_y_cm':1,'error_y_cm':0,'error_z_cm':float('nan')}}
    assert color_value(c,'qTot/qMax') is None
    assert color_value(c,'residual_y/error_y') is None
    assert color_value(c,'error_z') is None
    assert color_value(c,'error_y')==0
    assert color_value({'detector':'TPC','tpc_profile':c['tpc_profile']},'error_y') is None
    assert color_value({'features':{'q_tot':10}},'qTot') is None
    assert 'qTot/qMax' not in capabilities([c])


def test_aliases_and_features():
    c={'detector':'TPC','features':{'qTot':15,'qMax':3,'residual_z':-2,'error_z':.5}}
    assert color_value(c,'qTot/qMax')==5
    assert color_value(c,'residual_z/error_z')==-4
