import pytest
from alice_renderer.scene_presets import tpc_sectors_and_inner_wall,surround_lights
from alice_renderer.geometry_components import component_state
from alice_renderer.model import RenderSettings


def test_minimal_tpc_uses_native_tags_and_hides_unclassified_details():
    classes=[['parts/wall','structures/inner_wall'],['parts/sector','structures/readout'],
             ['parts/rod','structures/inner_rods'],['parts/unknown','structures/supports']]
    metadata={'detector':'TPC','components':{tag:{} for tags in classes for tag in tags},
              'groups':{'shared':{'classes':classes}}}
    choices=tpc_sectors_and_inner_wall(metadata)
    assert [component_state(tags,choices)[0] for tags in classes]==[True,True,False,False]
    with pytest.raises(ValueError,match='TPC'):tpc_sectors_and_inner_wall({'detector':'ITS'})


def test_surround_rig_covers_sides_and_both_ends_and_is_portable():
    lights=surround_lights((1.,2.,3.))
    cfg=RenderSettings(lights=lights).validate()
    assert len({light['name'] for light in cfg.lights})==10
    positions=[light['position_m'] for light in lights]
    assert min(p[0] for p in positions)<1<max(p[0] for p in positions)
    assert min(p[1] for p in positions)<2<max(p[1] for p in positions)
    assert min(p[2] for p in positions)<3<max(p[2] for p in positions)
    assert RenderSettings(**cfg.to_dict()).validate().lights==lights
