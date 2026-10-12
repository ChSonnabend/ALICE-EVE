"""Local scene history shared by the desktop app and Blender editor.

Only scene recipes and local references are stored; event/geometry data is never
copied. Favourites are immutable snapshots until explicitly removed.
"""
from __future__ import annotations
import copy, json, sqlite3, time, uuid
from pathlib import Path
from .model import RenderSettings
from .scene_config import load_config, recipe, save_config, resolve_settings

def default_path():return Path(__file__).resolve().parents[2]/'scene-library.local.sqlite'

class SceneLibrary:
    def __init__(self,path=None):
        self.path=Path(path or default_path());self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS recent_inputs (path TEXT PRIMARY KEY, updated REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS scenes (id TEXT PRIMARY KEY, config TEXT, title TEXT, kind TEXT, input TEXT, event TEXT, assets TEXT, updated REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS favourites (id TEXT PRIMARY KEY, config TEXT, title TEXT, kind TEXT, input TEXT, event TEXT, assets TEXT, updated REAL)')
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row;return db
    def recent_inputs(self):
        with self.connect() as db:
            return [r['path'] for r in db.execute('SELECT path FROM recent_inputs ORDER BY updated DESC, path LIMIT 12')]
    def remember_input(self,path):
        path=str(Path(path).expanduser().resolve())
        with self.connect() as db:
            db.execute('INSERT INTO recent_inputs VALUES (?,?) ON CONFLICT(path) DO UPDATE SET updated=excluded.updated',(path,time.time()))
            db.execute('DELETE FROM recent_inputs WHERE path NOT IN (SELECT path FROM recent_inputs ORDER BY updated DESC, path LIMIT 12)')
    def clear_recent_inputs(self):
        with self.connect() as db:db.execute('DELETE FROM recent_inputs')
    def register(self,path,*,kind='config',input_path='',event='',assets=None,title=None,updated=None):
        path=str(Path(path).resolve());data=load_config(path)
        supplied_input=input_path;input_path=str(input_path or data.get('defaults',{}).get('input',''));event=str(event or data.get('defaults',{}).get('event',''))
        if input_path:
            source=Path(input_path).expanduser()
            if not source.is_absolute() and not supplied_input:source=Path(path).parent/source
            input_path=str(source.resolve())
        title=title or (f'{kind.title()} · {event} · {Path(input_path).name}' if event else Path(path).stem)
        with self.connect() as db:
            db.execute('INSERT INTO scenes VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config,kind=excluded.kind,input=excluded.input,event=excluded.event,assets=excluded.assets,updated=excluded.updated',
                       (path,path,title,kind,input_path,event,json.dumps(assets or {}),updated or time.time()))
        return path
    def entries(self,favourites=False):
        with self.connect() as db:
            rows=db.execute('SELECT s.*, EXISTS(SELECT 1 FROM favourites f WHERE f.id=s.id) AS favourite FROM '+('favourites' if favourites else 'scenes')+' s ORDER BY updated DESC').fetchall()
        return [{**dict(r),'assets':json.loads(r['assets'])} for r in rows]
    def favourite(self,entry,title=None):
        target=self.path.parent/'scene-library'/'favourites'/(uuid.uuid4().hex+'.json')
        save_config(target,load_config(entry['config']))
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO favourites VALUES (?,?,?,?,?,?,?,?)',(entry['id'],str(target),title or entry['title'],entry['kind'],entry['input'],entry['event'],json.dumps(entry['assets']),time.time()))
        return target
    def unfavourite(self,entry):
        with self.connect() as db:db.execute('DELETE FROM favourites WHERE id=?',(entry['id'],))
    def settings(self,entry,*,reuse=False,assets=None,geometry_units=None):
        data=load_config(entry['config'])
        if not reuse:return resolve_settings(data,entry['config'],asset_overrides=entry['assets'])
        scene=copy.deepcopy(data['scene']);scene['highlight_track_ids']=[]
        scene.setdefault('include_ambiguous_tracks',True)
        scene.setdefault('data_glow_lighting',True)
        if 'camera_orbit_axis' not in scene:scene['camera_orbit_axis']='Z';scene.setdefault('elevation',22.)
        if geometry_units:scene['geometry_units']=geometry_units
        return RenderSettings(**scene,geometry_assets=dict(entry['assets'] if assets is None else assets)).validate()
    def record_job(self,folder,*,kind=None):
        folder=Path(folder);job=json.loads((folder/'job.json').read_text())
        values=dict(job['settings']);values.setdefault('include_ambiguous_tracks',True);values.setdefault('data_glow_lighting',True);cfg=RenderSettings(**values)
        meta_path=folder/'metadata.json'
        if meta_path.is_file():
            meta=json.loads(meta_path.read_text());cfg.camera_pose=meta.get('camera',cfg.camera_pose)
            for key in ('tracks','clusters'):
                legend=meta.get(key[:-1]+'_legend')
                if legend:cfg.color_ranges[key]=[legend['min'],legend['max']]
            event=meta.get('event_id','')
        else:event=''
        path=folder/'scene-session.json' if kind=='interactive' else folder/'scene-config.json'
        if not path.is_file():
            previous=folder/'scene-config.json'
            save_config(path,load_config(previous) if kind=='interactive' and previous.is_file() else recipe(cfg))
        return self.register(path,kind=kind or ('preview' if job.get('preview') else 'render'),input_path=job['event'],event=event,assets=cfg.geometry_assets,updated=path.stat().st_mtime)
    def discover(self,output):
        """Import older successful renders and editor sessions, without reading event data."""
        output=Path(output)
        folders=[*output.glob('render-*/event-*'),*output.glob('preview-*/event-*'),*output.glob('editor-*')]
        with self.connect() as db:known={r[0] for r in db.execute('SELECT config FROM scenes')}
        for folder in folders:
            interactive=folder.name.startswith('editor-')
            config=folder/('scene-session.json' if interactive else 'scene-config.json')
            if str(config.resolve()) in known:continue
            if not interactive and not (folder/'render.png').is_file():continue
            try:self.record_job(folder,kind='interactive' if interactive else None)
            except (OSError,ValueError,KeyError,TypeError):continue
