import json
from pathlib import Path
from alice_renderer.model import RenderSettings
from alice_renderer.runtime import geometry_only_input,fast_editor_settings,preflight
from alice_renderer.catalogue import load_event


def test_geometry_only_is_explicit_empty_valid_input(tmp_path):
    path=geometry_only_input(tmp_path)
    event=load_event(path)
    assert event['kind']=='geometry'
    assert event['tracks']==event['clusters']==[]
    cfg=RenderSettings(detectors=[],geometry=['TPC'],schematic=True)
    assert preflight(cfg,[event],{'version':[5,0],'devices':[{'type':'CPU','id':'cpu'}]},tmp_path)==[]


def test_fast_editor_uses_cache_without_mutating_final_settings(monkeypatch):
    from alice_renderer import structural_geometry
    monkeypatch.setattr(structural_geometry,'load',lambda *args:{})
    cfg=RenderSettings(geometry=['ITS','TPC','TRD'],geometry_assets={'ITS':'its','TPC':'tpc'})
    fast=fast_editor_settings(cfg)
    assert fast.geometry_lods=={'ITS':'structural','TPC':'structural'}
    assert cfg.geometry_lods=={}
    cfg.geometry_inner_masks={'ITS':{'radius_m':1}}
    assert 'ITS' not in fast_editor_settings(cfg).geometry_lods


def test_fast_editor_missing_cache_retains_geometry(monkeypatch):
    from alice_renderer import structural_geometry
    def missing(*args):raise ValueError('missing cache')
    monkeypatch.setattr(structural_geometry,'load',missing)
    cfg=RenderSettings(geometry=['ITS','TRD'],geometry_lod='full')
    assert fast_editor_settings(cfg).geometry_lods=={}
    cfg.geometry_lod='structural'
    assert fast_editor_settings(cfg).geometry_lods['TRD']=='full'
