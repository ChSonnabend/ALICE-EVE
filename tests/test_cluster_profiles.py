import numpy as np
import pytest
from alice_renderer.cluster_profiles import profile_axes
from alice_renderer.model import RenderSettings


def measured(vectors=((0,2,0),(0,0,3))):
    return {'detector':'TPC','tpc_profile':{'sigma_pad':2.,'sigma_time_bins':3.,'sigma_vectors_cm':vectors,'basis':'test Jacobian'}}


def test_profile_covariance_preserves_rotated_nonorthogonal_jacobian():
    c=measured(((1,2,0),(0,1,3)))
    size,basis=profile_axes(c,.03);u=np.array(basis);v=np.array(c['tpc_profile']['sigma_vectors_cm'])
    assert np.allclose(u@np.diag([size[0]**2,size[1]**2,0])@u.T,v.T@v)
    assert np.linalg.det(u)==pytest.approx(1)
    assert size[2]==.03


def test_missing_or_saturated_widths_are_not_invented():
    assert profile_axes({'detector':'TPC'},.03) is None
    c=measured();c['tpc_profile']['sigma_time_bins']=0
    assert profile_axes(c,.03) is None


@pytest.mark.parametrize('key,value',[('sigma_pad',-1),('sigma_time_bins',float('nan')),('basis',''),('sigma_vectors_cm',[[1,2]])])
def test_invalid_profiles_rejected(key,value):
    c=measured();c['tpc_profile'][key]=value
    with pytest.raises(ValueError):profile_axes(c,.03)


def test_profile_settings_validation():
    with pytest.raises(ValueError):RenderSettings(tpc_profile_scale=-1).validate()
    with pytest.raises(ValueError):RenderSettings(tpc_cluster_profile='invented').validate()
