import json,sys
from pathlib import Path
import pytest
from alice_renderer import cli,runtime
from alice_renderer.model import RenderSettings
from alice_renderer.scene_config import recipe,save_config
from alice_renderer.demo import generate

@pytest.mark.parametrize('local_list',[False,True])
def test_portable_video_cli_uses_instance_event_selection(tmp_path,monkeypatch,local_list):
    config=tmp_path/'scene.json';save_config(config,recipe(RenderSettings(video_enabled=True,schematic=True)))
    devices={'version':[5,0],'devices':[{'type':'CPU','id':'CPU','name':'CPU'}]}
    monkeypatch.setattr(cli,'probe',lambda _:devices)
    calls=[]
    monkeypatch.setattr(runtime,'render_video',lambda blender,paths,cfg,output,**kw:calls.append((paths,cfg,kw)) or tmp_path/'result')
    args=['alice-render','render-config',str(config),'--output',str(tmp_path/'renders'),'--cache',str(tmp_path/'cache')]
    if local_list:
        listing=tmp_path/'selection.local.json';listing.write_text(json.dumps(['first.json','second.json']))
        args+=['--event-files',str(listing),'--ffmpeg','/local/encoder']
    else:
        source=generate(tmp_path/'events.jsonl');args+=['--input',str(source),'--events','ordinal:2,ordinal:0']
    monkeypatch.setattr(sys,'argv',args);cli.main()
    paths,cfg,kw=calls[0];assert cfg.video_enabled and len(paths)==2
    if local_list:
        assert paths==[tmp_path/'first.json',tmp_path/'second.json'] and kw['ffmpeg']=='/local/encoder'
    else:
        from alice_renderer.catalogue import load_event
        assert [load_event(p)['id'] for p in paths]==['SYNTHETIC-3','SYNTHETIC-1']
    assert not json.loads(config.read_text())['defaults']

@pytest.mark.parametrize('detail',[None,'current'])
def test_config_render_defaults_to_full_surfaces_unless_recipe_detail_is_requested(tmp_path,monkeypatch,detail):
    asset=tmp_path/'TPC.blend';asset.write_bytes(b'geometry-contract-fixture')
    data=recipe(RenderSettings(video_enabled=True,detectors=[],geometry=['TPC'],geometry_assets={'TPC':str(asset)},geometry_lod='simplified'))
    config=tmp_path/'scene.json';save_config(config,data)
    selection=tmp_path/'selection.local.json';selection.write_text(json.dumps(['a.json','b.json']))
    monkeypatch.setattr(cli,'probe',lambda _:dict(version=[5,0],devices=[dict(type='CPU',id='CPU')]))
    calls=[];monkeypatch.setattr(runtime,'render_video',lambda blender,paths,cfg,output,**kw:calls.append(cfg) or tmp_path/'output')
    args=['alice-render','render-config',str(config),'--event-files',str(selection)]
    if detail:args+=['--geometry-detail',detail]
    monkeypatch.setattr(sys,'argv',args);cli.main()
    assert calls[0].geometry_lods.get('TPC',calls[0].geometry_lod)==('full' if detail is None else 'simplified')

@pytest.mark.parametrize('preview,detail,expected',[(False,None,'full'),(True,None,'simplified'),(False,'current','simplified')])
def test_catalogue_render_upgrades_only_final_geometry_by_default(tmp_path,monkeypatch,preview,detail,expected):
    from alice_renderer.catalogue import Catalogue
    source=generate(tmp_path/'events.jsonl');cat=Catalogue.build(source,tmp_path/'cache')
    settings=tmp_path/'settings.json';settings.write_text(json.dumps(RenderSettings(geometry=['TPC'],schematic=True,geometry_lod='simplified').to_dict()))
    calls=[];monkeypatch.setattr(cli,'render_events',lambda blender,paths,cfg,output,**kw:calls.append(cfg) or tmp_path/'output')
    args=['alice-render','render',str(cat.folder),'--events','0','--settings',str(settings)]
    if preview:args+=['--preview']
    if detail:args+=['--geometry-detail',detail]
    monkeypatch.setattr(sys,'argv',args);cli.main()
    assert calls[0].geometry_lods.get('TPC',calls[0].geometry_lod)==expected
