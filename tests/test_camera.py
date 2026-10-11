import pytest
from pathlib import Path
from alice_renderer.camera import orbit_position
from alice_renderer.model import RenderSettings
from alice_renderer.scene_config import recipe,resolve_settings

def test_new_orbit_uses_y_as_vertical_and_xz_as_horizontal():
    cfg=RenderSettings();assert cfg.camera_orbit_axis=='Y' and cfg.elevation==0
    assert orbit_position(0,0,10,[1,2,3])==[11,2,3]
    assert orbit_position(90,0,10,[1,2,3])==pytest.approx([1,2,13])
    assert orbit_position(0,90,10,[1,2,3])==pytest.approx([1,12,3])

def test_old_recipes_preserve_legacy_orbit_and_explicit_camera_pose():
    data=recipe(RenderSettings());assert resolve_settings(data,Path('scene.json')).camera_orbit_axis=='Y'
    del data['scene']['camera_orbit_axis']
    cfg=resolve_settings(data,Path('scene.json'));assert cfg.camera_orbit_axis=='Z'
    assert orbit_position(90,0,10,[1,2,3],cfg.camera_orbit_axis)==pytest.approx([1,12,3])
    assert orbit_position(0,90,10,[1,2,3],cfg.camera_orbit_axis)==pytest.approx([1,2,13])
    with pytest.raises(ValueError):RenderSettings(camera_orbit_axis='X').validate()

def test_local_default_upgrade_preserves_custom_cameras():
    from alice_renderer.camera import upgrade_local_camera
    old={'azimuth':-55.,'elevation':22.,'roll':0.}
    updated=upgrade_local_camera(old)
    assert updated['camera_orbit_axis']=='Y' and updated['elevation']==0
    assert old['elevation']==22 # no mutation of the saved preferences
    custom=upgrade_local_camera(dict(old,roll=27.))
    assert custom['camera_orbit_axis']=='Z' and custom['roll']==27 and custom['elevation']==22
    pose={'matrix_world':[[1,0,0,4],[0,1,0,5],[0,0,1,6],[0,0,0,1]],'lens':48,'ortho_scale':10}
    assert upgrade_local_camera(dict(old,camera_pose=pose))['camera_pose']==pose

def test_minimal_legacy_recipe_keeps_old_elevation():
    cfg=resolve_settings({'schema':'alice-eve-scene','version':1,'scene':{},'geometry':{},'defaults':{}},Path('scene.json'))
    assert cfg.elevation==22 and cfg.camera_orbit_axis=='Z'
