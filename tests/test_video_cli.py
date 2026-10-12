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
