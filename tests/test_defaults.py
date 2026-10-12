import pytest
from alice_renderer.defaults import COMMISSIONING_PRESET,startup_settings,commissioning_settings
from alice_renderer.scene_config import load_config,LOCAL_FIELDS
from alice_renderer.camera import orbit_position


def test_portable_startup_preset_has_no_local_inputs_or_quality():
    data=load_config(COMMISSIONING_PRESET)
    assert data['defaults']=={} and not set(data['scene'])&LOCAL_FIELDS
    cfg=commissioning_settings()
    assert cfg.geometry_assets=={} and cfg.detectors==cfg.geometry==['ITS','TPC']
    assert cfg.mode=='both' and cfg.geometry_lod=='full' and not cfg.schematic
    assert cfg.geometry_openings.get('ITS')==180. and cfg.geometry_openings.get('TPC')==0.
    assert cfg.view_transform=='Standard' and cfg.camera_lens_mm==cfg.camera_pose['lens']
    # Orbit distance is in centimetres in settings, metres in the worker.
    position=orbit_position(cfg.azimuth,cfg.elevation,cfg.distance_cm*.01,[v*.01 for v in cfg.target_cm],'Y')
    assert position==pytest.approx([row[3] for row in cfg.camera_pose['matrix_world'][:3]],abs=1.e-6)


def test_default_style_clone_uses_current_local_alignment_and_independent_instances():
    a=commissioning_settings({'TPC':'/local/TPC.blend'},'cm');b=commissioning_settings()
    assert a.geometry_assets=={'TPC':'/local/TPC.blend'} and a.geometry_units=='cm'
    a.colors['TPC']='#ffffff';a.camera_pose['lens']=99
    assert b.colors['TPC']!='#ffffff' and b.camera_pose['lens']!=99


def test_startup_keeps_reviewed_camera_with_reduced_tpc_and_surround_lights():
    cfg=startup_settings()
    assert cfg.camera_lens_mm==16 and cfg.roll==13.3
    assert not cfg.geometry_inner_masks.get('TPC') and not cfg.geometry_exclusions.get('TPC')
    parts=cfg.geometry_components['TPC']
    assert parts['parts/TPC_ICVM'] and parts['parts/TPC_IROCB']
    assert not any(parts[key] for key in ('parts/TPC_IGR1','parts/TPC_INPLL','parts/TPC_ring','parts/TPC_rodl','parts/TPC_MMHC'))
    from alice_renderer.scene_presets import SURROUND_LIGHT_PREFIX
    assert sum(light.get('name','').startswith(SURROUND_LIGHT_PREFIX) for light in cfg.lights)==10
    assert cfg.geometry_openings.get('ITS')==90. and cfg.geometry_openings.get('TPC')==90.
