"""Reconcile an export against O2's independent, unfiltered PV inventory."""
from __future__ import annotations
import gzip, hashlib, json, math, sqlite3, tempfile
from pathlib import Path

def event_header(line):
    """Read native enumeration metadata without materializing millions of hits.

General JSON key order remains supported by the full-parser fallback. Scientific
object validation belongs to the catalogue, not the enumeration counter.
"""
    offset=line[:16384].find(',"tracks":[')
    if offset>0:
        try:
            header=json.loads(line[:offset]+'}')
            if all(k in header for k in ('schema_version','kind','units','id','run','timeframe','orbit','primary_vertex','vertex')):return header
        except json.JSONDecodeError:pass
    return json.loads(line)


def _integer(value, name):
    if not isinstance(value,int) or isinstance(value,bool) or value<0:
        raise ValueError(f'{name} must be a nonnegative integer')
    return value


def _identity(record, *, event=False):
    return tuple(_integer(record.get(key),key) for key in
                 ('run','timeframe' if event else 'tf_counter','orbit'))


def reconcile_export(events: Path, inventory: Path, *, expected_timeframes: int,
                     expected_identities=None, cancelled=lambda:False) -> dict:
    """Disk-backed identity check. Empty vertices and empty TFs must be preserved.

    Does not certify calibration/physics; it certifies collision enumeration only.
    events.jsonl must carry run/timeframe/orbit/primary_vertex and global-cm PV XYZ.
    The inventory completion marker is created only by O2's endOfStream callback.
    """
    events,inventory=Path(events),Path(inventory)
    expected_timeframes=_integer(expected_timeframes,'expected_timeframes')
    completion=json.loads(Path(str(inventory)+'.complete.json').read_text())
    if completion.get('schema_version')!=1:raise ValueError('Unsupported inventory completion schema')
    inventory_before=(inventory.stat().st_size,inventory.stat().st_mtime_ns)
    events_before=(events.stat().st_size,events.stat().st_mtime_ns)
    seen=set();vertices=exported=0;digest=hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix='alice-enumeration-') as temporary:
        with sqlite3.connect(str(Path(temporary)/'vertices.sqlite')) as database:
            database.execute('CREATE TABLE vertices (run INTEGER, tf INTEGER, orbit INTEGER, pv INTEGER, x REAL, y REAL, z REAL, exported INTEGER DEFAULT 0, PRIMARY KEY(run,tf,orbit,pv))')
            database.execute('CREATE TABLE event_ids (id TEXT PRIMARY KEY)')
            with inventory.open('rb') as stream:
                for line in stream:
                    if cancelled():raise InterruptedError('Enumeration verification cancelled')
                    digest.update(line)
                    if not line.strip():continue
                    record=json.loads(line)
                    if record.get('schema_version')!=1:raise ValueError('Unsupported PV inventory schema')
                    key=_identity(record)
                    if key in seen:raise ValueError(f'Duplicate inventory timeframe: {key}')
                    seen.add(key)
                    pvs=record.get('vertices')
                    if not isinstance(pvs,list) or len(pvs)!=_integer(record.get('vertex_count'),'vertex_count'):
                        raise ValueError('Inventory vertex count does not match its records')
                    for ordinal,pv in enumerate(pvs):
                        if pv.get('index')!=ordinal:raise ValueError('Inventory PV indices must be contiguous from zero')
                        position=pv.get('position_cm',[])
                        if len(position)!=3 or not all(math.isfinite(v) for v in position):raise ValueError('Invalid inventory vertex position')
                        database.execute('INSERT INTO vertices (run,tf,orbit,pv,x,y,z) VALUES (?,?,?,?,?,?,?)',(*key,ordinal,*position))
                    vertices+=len(pvs)
            if len(seen)!=expected_timeframes:raise ValueError(f'Processed {len(seen)} of {expected_timeframes} input timeframes')
            if expected_identities is not None and seen!=set(expected_identities):raise ValueError('Inventory timeframe identifiers differ from the input')
            if completion.get('timeframes')!=len(seen) or completion.get('vertices')!=vertices:
                raise ValueError('Inventory completion counts do not match its contents')
            with (gzip.open(events,'rt') if events.suffix=='.gz' else events.open()) as stream:
                for line in stream:
                    if cancelled():raise InterruptedError('Enumeration verification cancelled')
                    if not line.strip():continue
                    event=event_header(line)
                    if event.get('schema_version')!=1 or event.get('kind')!='collision' or event.get('units')!='cm':
                        raise ValueError('Expected canonical collision events in global centimetres')
                    identity=(*_identity(event,event=True),_integer(event.get('primary_vertex'),'primary_vertex'))
                    row=database.execute('SELECT x,y,z,exported FROM vertices WHERE run=? AND tf=? AND orbit=? AND pv=?',identity).fetchone()
                    if row is None:raise ValueError(f'Export contains a PV absent from reconstruction: {identity}')
                    if row[3]:raise ValueError(f'Collision exported more than once: {identity}')
                    position=event.get('vertex',[])
                    if len(position)!=3 or not all(math.isfinite(v) and math.isclose(v,expected,abs_tol=1e-5,rel_tol=1e-6) for v,expected in zip(position,row[:3])):
                        raise ValueError(f'Exported PV coordinates differ from reconstruction: {identity}')
                    name=event.get('id')
                    if not isinstance(name,str) or not name.strip():raise ValueError('Event identifier is missing')
                    try:database.execute('INSERT INTO event_ids VALUES (?)',(name,))
                    except sqlite3.IntegrityError as exc:raise ValueError(f'Duplicate event identifier: {name}') from exc
                    database.execute('UPDATE vertices SET exported=1 WHERE run=? AND tf=? AND orbit=? AND pv=?',identity)
                    exported+=1
            missing=database.execute('SELECT COUNT(*) FROM vertices WHERE exported=0').fetchone()[0]
            if missing:raise ValueError(f'Export omitted {missing} reconstructed primary vertices (including any empty vertices)')
    for path,before in ((inventory,inventory_before),(events,events_before)):
        stat=path.stat()
        if before!=(stat.st_size,stat.st_mtime_ns):raise ValueError('Export/inventory changed during verification')
    return dict(timeframes_processed=len(seen),primary_vertices_seen=vertices,
                primary_vertices_exported=exported,event_count=exported,
                inventory_sha256=digest.hexdigest())
