"""Native output QA: full-HD Eevee MP4 and an exact stopped playback frame.

Run with Blender --background --python-exit-code 1 --python this_file -- --output DIR.
"""
import argparse,json,sys,shutil
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parents[1]/'src/alice_renderer/blender')]
import bpy,worker
from alice_renderer.model import RenderSettings,validate_event
from alice_renderer.video import schedule,header
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
root=a.output;root.mkdir(parents=True,exist_ok=True);events=[];paths=[]
for i in range(2):
    event=validate_event(dict(schema_version=1,units='cm',kind='synthetic',id=f'output-{i}',vertex=[0,0,0],tracks=[dict(id=str(i),detectors=['TPC'],points=[[0,0,0],[100,0,0],[200,i*100,0]])],clusters=[dict(id='hit',detector='TPC',position=[100,0,0],track_id=str(i))]))
    path=root/f'event-{i}.json';path.write_text(json.dumps(event));events.append(event);paths.append(str(path.resolve()))
asset=Path(__file__).resolve().parents[1]/'geometry/run-560067/TPC.blend'
cfg=RenderSettings(video_enabled=True,video_fps=2,video_interval_s=1,video_speed_m_s=3,detectors=['TPC'],geometry=['TPC'],geometry_lods={'TPC':'proxy'},geometry_assets={'TPC':str(asset)},geometry_units='m',render_engine='BLENDER_EEVEE',samples=8,width=1920,height=1080,save_blend=False,cluster_radius_cm=5)
plan=schedule(events,cfg.to_dict())
for kind in ('movie','still'):
    folder=root/kind;folder.mkdir(exist_ok=True)
    payload=dict(event=paths[0],events=paths,video_headers=[header(e) for e in events],video_plan=plan,output=str(folder),settings=cfg.to_dict(),required_track_detectors=['TPC'])
    if kind=='movie':payload['ffmpeg']=shutil.which('ffmpeg')
    else:payload['video_frame']=3  # Second collision, half a second into propagation.
    job=folder/'job.json';job.write_text(json.dumps(payload));worker.render(job)
    image=bpy.data.images.load(str(folder/'render.png'));assert tuple(image.size)==(1920,1080);bpy.data.images.remove(image)
    if kind=='movie':assert (folder/'video.mp4').stat().st_size>1000
    else:
        metadata=json.loads((folder/'metadata.json').read_text())
        assert metadata['video_frame']==dict(frame=3,fps=2,event='output-1',age_s=.5)
        assert not (folder/'video.mp4').exists()
print('FULL HD MOVIE AND STOPPED FRAME OUTPUT QA PASSED',flush=True)
