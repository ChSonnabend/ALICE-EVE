"""Start video from an ordinary multi-event editor; Play clears sidebar holds."""
import json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender'))
import bpy,worker,editor
from alice_renderer.model import RenderSettings,validate_event
from alice_renderer.video import header

with tempfile.TemporaryDirectory(prefix='alice-play-entry-') as tmp:
    root=Path(tmp);paths=[];events=[]
    for i in range(2):
        event=validate_event(dict(schema_version=1,units='cm',kind='synthetic',id=str(i),vertex=[0,0,0],tracks=[dict(id=str(i),detectors=['TPC'],points=[[100,0,0],[200,0,0]])],clusters=[]))
        path=root/f'{i}.json';path.write_text(json.dumps(event));paths.append(str(path));events.append(event)
    cfg=RenderSettings(video_enabled=False,video_fps=8,detectors=['TPC'],geometry=['TPC'],schematic=True)
    payload=dict(event=paths[0],events=paths,video_headers=[header(e) for e in events],output=str(root),settings=cfg.to_dict(),blender={'version':list(bpy.app.version),'devices':[{'type':'CPU'}]})
    job=root/'job.json';job.write_text(json.dumps(payload));worker.render(job,True)
    assert not editor.JOB.get('video_player')
    detector=bpy.data.collections['TPC'].objects[0];identity=(detector.as_pointer(),detector.data.as_pointer())
    assert bpy.ops.alice_eve.play_video()=={'FINISHED'}
    player=editor.JOB['video_player'];assert player.playing and bpy.context.scene.alice_eve.video_enabled
    player.hold_controls(True);assert player.held_at is not None
    bpy.ops.alice_eve.play_video();assert player.playing and player.held_at is None
    player.anchor=time.monotonic()-1.01;player.timer();assert player.event['id']=='1'
    assert (detector.as_pointer(),detector.data.as_pointer())==identity
    bpy.ops.alice_eve.stop_video();assert not player.playing
    print('GUI / STILL EDITOR VIDEO ENTRY BLENDER QA PASSED')
