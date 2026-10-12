"""Streaming import into an atomic on-disk catalogue, one payload per event."""
from __future__ import annotations
import gzip, hashlib, json, os, shutil, sqlite3, tempfile
from pathlib import Path
from .model import validate_event, capabilities

def fingerprint(path: Path) -> str:
    stat = path.stat()
    digest = hashlib.sha256(f'{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}'.encode())
    if path.is_dir():
        for child in sorted([*path.glob('*.json'),*path.glob('*.jsonl'),*path.glob('*.json.gz'),*path.glob('*.jsonl.gz')]):
            data=child.stat();digest.update(f'{child.name}:{data.st_size}:{data.st_mtime_ns}'.encode())
    if path.is_file():
        with path.open('rb') as stream:
            digest.update(stream.read(65536))
            if stat.st_size>65536:
                stream.seek(-65536,os.SEEK_END); digest.update(stream.read(65536))
    return digest.hexdigest()[:24]

def iter_json(path: Path):
    import ijson
    if path.is_dir():
        if (path/'manifest.json').exists():
            manifest=json.loads((path/'manifest.json').read_text())
            name=manifest.get('events_file','events.jsonl')
            if manifest.get('complete') is True and name in ('events.jsonl','events.jsonl.gz'):
                yield from iter_json(path/name);return
        for item in sorted(path.glob('*.json')): yield from iter_json(item)
        for item in sorted([*path.glob('*.jsonl'),*path.glob('*.json.gz'),*path.glob('*.jsonl.gz')]): yield from iter_json(item)
        return
    opener=gzip.open if path.suffix=='.gz' else open
    if path.name.endswith(('.jsonl','.jsonl.gz')):
        with opener(path,'rt') as stream:
            for line in stream:
                if line.strip(): yield json.loads(line)
        return
    with opener(path,'rb') as stream:
        prefix = stream.read(4096).lstrip(); stream.seek(0)
        if prefix.startswith(b'['): yield from ijson.items(stream,'item',use_float=True)
        elif prefix.startswith(b'{'):
            # Inspect parser keys rather than searching text, which can include braces/"events" in strings.
            parser = ijson.parse(stream)
            keys=[]
            for p,e,v in parser:
                if p=='' and e=='map_key': keys.append(v)
                if 'events' in keys or 'schema_version' in keys or 'mTracks' in keys or 'Tracks' in keys: break
            stream.seek(0)
            if 'events' in keys: yield from ijson.items(stream,'events.item',use_float=True)
            else: yield json.load(stream)
        else: raise ValueError('Expected JSON event, event array or JSON Lines')

class Catalogue:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.db = self.folder/'catalogue.sqlite'
        if not self.db.is_file(): raise ValueError('No completed event catalogue')

    @classmethod
    def build(cls, source: Path, cache: Path, *, convert=None, progress=lambda s:None, cancelled=lambda:False,aod_options=None):
        source,cache = Path(source),Path(cache)
        if source.suffix.lower()=='.root':
            from .aod import build_catalogue
            return build_catalogue(source,cache,options=aod_options,progress=progress,cancelled=cancelled)
        if source.is_dir() and (source/'manifest.json').is_file():
            manifest=json.loads((source/'manifest.json').read_text())
            name=manifest.get('events_file','events.jsonl')
            if manifest.get('complete') is True and name in ('events.jsonl','events.jsonl.gz'):
                source=source/name
        cache.mkdir(parents=True,exist_ok=True)
        key = fingerprint(source)
        destination = cache/key
        if (destination/'catalogue.sqlite').exists():
            existing=cls(destination);existing.refresh_calorimeter_capabilities(progress,cancelled);return existing
        staging = Path(tempfile.mkdtemp(prefix='index-',dir=cache))
        connection=None
        try:
            connection = sqlite3.connect(staging/'catalogue.sqlite')
            connection.execute('CREATE TABLE events (ordinal INTEGER PRIMARY KEY, event_id TEXT, kind TEXT, run TEXT, timeframe TEXT, ntracks INTEGER, nclusters INTEGER, detectors TEXT, track_fields TEXT, cluster_fields TEXT, filename TEXT, contributors INTEGER)')
            connection.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)')
            count=0
            for raw in iter_json(source):
                if cancelled(): raise InterruptedError('Import cancelled')
                event = validate_event(convert(raw) if convert else raw)
                filename=f'event-{count:08d}.json.gz'
                with gzip.open(staging/filename,'wt',compresslevel=3) as file:
                    file.write(json.dumps(event,allow_nan=False,separators=(',',':')))
                connection.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(count,str(event['id']),event['kind'],str(event.get('run','')),str(event.get('timeframe','')),len(event['tracks']),len(event['clusters']),json.dumps(event['available_detectors']),json.dumps(capabilities(event['tracks'])),json.dumps(capabilities(event['clusters'])),filename,event.get('contributors')))
                count+=1
                if count%10==0: progress(f'Indexed {count} events')
                # Release the previous large record before parsing the next one.
                del event,raw
            if not count: raise ValueError('No events found; reconstruction/export may have produced no collisions')
            connection.execute('INSERT INTO metadata VALUES (?,?)',('source',str(source.resolve())))
            connection.execute('INSERT INTO metadata VALUES (?,?)',('source_fingerprint',key))
            connection.execute('INSERT INTO metadata VALUES (?,?)',('calorimeter_capabilities','2'))
            connection.commit(); connection.close();connection=None
            if source.is_file() and fingerprint(source)!=key: raise ValueError('Input changed while being read; wait for copying/download to finish')
            if destination.exists(): shutil.rmtree(staging)
            else: staging.rename(destination)
            progress(f'Indexed {count} events')
            return cls(destination)
        except BaseException:
            if connection is not None:connection.close()
            shutil.rmtree(staging,ignore_errors=True)
            raise

    def refresh_calorimeter_capabilities(self,progress=lambda s:None,cancelled=lambda:False):
        """Update old scalar indices once, retaining their cached event payloads."""
        import ijson
        from .calorimeter_towers import CALORIMETERS
        from .cluster_colors import value
        with sqlite3.connect(self.db) as db:
            if db.execute("SELECT 1 FROM metadata WHERE key='calorimeter_capabilities' AND value='2'").fetchone():return
            progress('Checking existing calorimeter energy / amplitude fields')
            for ordinal,detectors,count,filename,fields in db.execute('SELECT ordinal,detectors,nclusters,filename,cluster_fields FROM events').fetchall():
                if cancelled():raise InterruptedError('Calorimeter indexing cancelled')
                if not count or not set(json.loads(detectors)).intersection(CALORIMETERS):continue
                supported=set(json.loads(fields))-{'energy','amplitude'};path=self.folder/filename
                with gzip.open(path,'rb') as stream:
                    for index,cluster in enumerate(ijson.items(stream,'clusters.item',use_float=True)):
                        if index%10000==0 and cancelled():raise InterruptedError('Calorimeter indexing cancelled')
                        for field in ('energy','amplitude'):
                            if field not in supported and value(cluster,field) is not None:supported.add(field)
                        if {'energy','amplitude'}<=supported:break
                db.execute('UPDATE events SET cluster_fields=? WHERE ordinal=?',(json.dumps(sorted(supported)),ordinal))
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('calorimeter_capabilities','2')")

    def rows(self) -> list[dict]:
        with sqlite3.connect(self.db) as db:
            db.row_factory=sqlite3.Row
            rows=[dict(row) for row in db.execute('SELECT * FROM events ORDER BY ordinal')]
            if db.execute("SELECT value FROM metadata WHERE key='aod_version'").fetchone():return rows
        # Older catalogues lack the new matching capability. Inspect only a small
        # track prefix, preserving the already validated payloads and index.
        from .object_selection import matching_value
        import ijson
        for row in rows:
            path=self.folder/row['filename']
            if 'contributors' not in row:
                # Native records put the PV header before tracks. Read only that
                # prefix for old caches; never scan millions of clusters for it.
                row['contributors']=None
                with (gzip.open(path,'rb') if path.suffix=='.gz' else path.open('rb')) as stream:
                    for prefix,kind,value in ijson.parse(stream):
                        if prefix=='contributors' and kind=='number':row['contributors']=int(value);break
                        if prefix in ('tracks','clusters') and kind=='start_array':break
            if 'matching' in json.loads(row['track_fields']) or not row['ntracks']:continue
            with (gzip.open(path,'rb') if path.suffix=='.gz' else path.open('rb')) as stream:
                for count,track in enumerate(ijson.items(stream,'tracks.item',use_float=True)):
                    if matching_value(track) is not None:
                        row['track_fields']=json.dumps(json.loads(row['track_fields'])+['matching'])
                        if row['nclusters'] and any(k in json.loads(row['cluster_fields']) for k in ('pt','p')):row['cluster_fields']=json.dumps(json.loads(row['cluster_fields'])+['matching'])
                        break
                    if count>=7:break
        return rows

    def event_path(self, ordinal: int,*,progress=lambda s:None,cancelled=lambda:False) -> Path:
        with sqlite3.connect(self.db) as db:
            row=db.execute('SELECT filename FROM events WHERE ordinal=?',(int(ordinal),)).fetchone()
            if not row: raise KeyError(ordinal)
            path=self.folder/row[0]
            if db.execute("SELECT value FROM metadata WHERE key='aod_version'").fetchone():
                from .aod import materialize
                return materialize(self,int(ordinal),progress=progress,cancelled=cancelled)
            return path

    def load(self, ordinal: int) -> dict:
        return load_event(self.event_path(ordinal))

def load_event(path):
    path=Path(path)
    with (gzip.open(path,'rt') if path.suffix=='.gz' else path.open()) as stream:event=json.load(stream)
    from .object_selection import annotate_matching
    return annotate_matching(event)
