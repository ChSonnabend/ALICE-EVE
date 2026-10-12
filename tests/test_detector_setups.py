import json
from pathlib import Path
from alice_renderer.defaults import detector_settings,SETUP_PRESETS


def test_setups_preserve_saved_camera_and_light_recipe():
    base=detector_settings('ALICE2')
    for name in SETUP_PRESETS:
        cfg=detector_settings(name)
        for key in ['camera_pose','lights','world_strength','view_transform','exposure','roll','track_emission','cluster_emission']:
            assert getattr(cfg,key)==getattr(base,key)
        assert all(Path(p).is_file() for p in cfg.geometry_assets.values())
        if name=='ALICE3':assert cfg.detectors==[] and 'TPC' not in cfg.geometry
        if name=='ALICE2 + ITS3':assert cfg.geometry_lods['ITS']=='full'


def test_alice3_has_own_detector_identity_and_mapped_opening():
    cfg=detector_settings('ALICE3');base=detector_settings('ALICE2')
    assert cfg.detector_setup=='ALICE3'
    assert cfg.geometry_openings['TRK']==base.geometry_openings['ITS']
    assert cfg.colors_linear['TRK']==base.colors_linear['ITS']
