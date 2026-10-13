"""Persistent, detached render supervision shared by the desktop and Blender.

Stop suspends the live process tree; Continue resumes it. Restart creates a new
attempt. Paused GPU/RAM state is retained in memory, not checkpointed to disk.
"""
from __future__ import annotations
import argparse,json,os,re,sqlite3,subprocess,sys,time,uuid
from pathlib import Path

TERMINAL={'completed','failed','finished','interrupted'}


def connect(library):
    path=Path(library);path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=10);db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS render_jobs (id TEXT PRIMARY KEY, spec TEXT NOT NULL, state TEXT NOT NULL, request TEXT)')
    return db


def get(library,identity):
    with connect(library) as db:row=db.execute('SELECT * FROM render_jobs WHERE id=?',(identity,)).fetchone()
    if row is None:raise ValueError('Unknown render job')
    return dict(id=row['id'],spec=json.loads(row['spec']),state=json.loads(row['state']),request=row['request'])


def jobs(library):
    with connect(library) as db:rows=db.execute('SELECT * FROM render_jobs').fetchall()
    items=[dict(id=r['id'],spec=json.loads(r['spec']),state=json.loads(r['state']),request=r['request']) for r in rows]
    return sorted(items,key=lambda j:(j['state']['status'] in TERMINAL,-j['spec']['created']))


def update(library,identity,**values):
    with connect(library) as db:
        db.execute('BEGIN IMMEDIATE')
        state=json.loads(db.execute('SELECT state FROM render_jobs WHERE id=?',(identity,)).fetchone()[0])
        state.update(values,updated=time.time());db.execute('UPDATE render_jobs SET state=? WHERE id=?',(json.dumps(state),identity))
    return state


def live(pid,created):
    import psutil
    if pid is None or created is None:return None
    try:
        p=psutil.Process(pid)
        return p if abs(p.create_time()-created)<.01 and p.status()!=psutil.STATUS_ZOMBIE else None
    except (psutil.Error,TypeError):return None


def start_supervisor(library,identity):
    spec=get(library,identity)['spec']
    env=os.environ.copy();env['PYTHONUNBUFFERED']='1'
    # Blender's bundled interpreter can submit work to the external app Python.
    source=str(Path(__file__).resolve().parents[1])
    env['PYTHONPATH']=source+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    log=Path(spec['folder'])/'supervisor.log'
    with log.open('a') as stream:
        subprocess.Popen([spec['python'],'-m','alice_renderer.render_jobs','--library',str(Path(library).resolve()),'--run',identity],cwd=spec['cwd'],stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,env=env)


def submit(command,*,library,python=None,cwd=None,title='Render',adopt=None,progress_log=None):
    identity=uuid.uuid4().hex;folder=Path(library).resolve().parent/'scene-library'/'jobs'/identity;folder.mkdir(parents=True)
    spec=dict(command=[str(v) for v in command],python=python or sys.executable,cwd=str(Path(cwd or os.getcwd()).resolve()),title=title,folder=str(folder),created=time.time(),adopted=bool(adopt))
    state=dict(status='starting',progress=0,message='Starting background supervisor',attempt=0,log=str(progress_log or folder/'attempt-1.log'))
    if adopt:state.update(pid=adopt.pid,process_created=adopt.create_time(),status='paused' if adopt.status()=='stopped' else 'running',attempt=1,message='Attached to existing render')
    with connect(library) as db:db.execute('INSERT INTO render_jobs VALUES (?,?,?,NULL)',(identity,json.dumps(spec),json.dumps(state)))
    try:start_supervisor(library,identity)
    except Exception as exc:update(library,identity,status='failed',message=str(exc));raise
    return identity


def control(library,identity,action):
    if action not in ('stop','continue','restart'):raise ValueError('Unknown render action')
    item=get(library,identity);state=item['state']
    if action=='stop' and state['status'] not in ('running','starting'):raise ValueError('Only running jobs can be stopped')
    if action=='continue' and state['status']!='paused':raise ValueError('Only paused jobs can continue; interrupted jobs must restart')
    with connect(library) as db:db.execute('UPDATE render_jobs SET request=? WHERE id=?',(action,identity))
    if not live(state.get('supervisor_pid'),state.get('supervisor_created')):start_supervisor(library,identity)


def suspend_tree(root):
    import psutil
    paused=[]
    def pause(p):
        try:
            p.suspend();paused.append((p.pid,p.create_time()))
            for child in p.children():pause(child)
        except psutil.NoSuchProcess:pass
    try:pause(root)
    except psutil.Error:
        resume_tree(paused);raise
    return paused


def resume_tree(paused):
    import psutil
    for pid,created in reversed(paused):
        p=live(pid,created)
        if p:
            try:p.resume()
            except psutil.NoSuchProcess:pass


def terminate_tree(root,paused=()):
    import psutil
    processes=[root]+root.children(recursive=True)
    # Kill a stopped tree directly: resuming it before termination can render or
    # spawn new children. psutil handles the platform-specific termination API.
    for p in reversed(processes):
        try:p.kill()
        except psutil.NoSuchProcess:pass
    psutil.wait_procs(processes,timeout=5)


def log_progress(path,offset,state):
    from .render_progress import sample_percent
    try:
        with Path(path).open(errors='replace') as stream:
            if Path(path).stat().st_size<offset:offset=0
            stream.seek(offset)
            for line in stream:
                line=line.strip()
                if not line:continue
                match=re.search(r'Render progress: (\d+)%',line)
                frames=re.search(r'ALICE_FRAME (\d+)/(\d+)',line)
                percent=int(match[1]) if match else int(frames[1])*100//max(1,int(frames[2])) if frames else sample_percent(line)
                if percent is not None:state['progress']=min(99,max(state['progress'],percent))
                state['message']=line[-240:]
            return stream.tell()
    except OSError:return offset


def supervise(library,identity):
    import psutil
    me=psutil.Process();item=get(library,identity)
    # Only one supervisor may claim the job, including concurrent GUI restarts.
    with connect(library) as db:
        db.execute('BEGIN IMMEDIATE');state=json.loads(db.execute('SELECT state FROM render_jobs WHERE id=?',(identity,)).fetchone()[0])
        if live(state.get('supervisor_pid'),state.get('supervisor_created')):return
        state.update(supervisor_pid=me.pid,supervisor_created=me.create_time())
        db.execute('UPDATE render_jobs SET state=? WHERE id=?',(json.dumps(state),identity))
    spec=item['spec'];process=None;root=live(state.get('pid'),state.get('process_created'));paused=state.get('paused_processes',[]);offset=0
    def launch():
        nonlocal process,root,offset,state,paused
        attempt=state['attempt']+1;log=Path(spec['folder'])/f'attempt-{attempt}.log'
        env=os.environ.copy();env['PYTHONUNBUFFERED']='1'
        command=list(spec['command'])
        # An adopted raw Blender worker writes to a fixed output directory.
        # Give each new attempt its own payload/output, preserving the original.
        if '--job' in command and any(Path(v).name=='worker.py' for v in command):
            index=command.index('--job')+1
            payload=json.loads(Path(command[index]).read_text())
            output=Path(spec['folder'])/f'attempt-{attempt}'
            output.mkdir(parents=True,exist_ok=True);payload['output']=str(output)
            job=output/'job.json';job.write_text(json.dumps(payload))
            command[index]=str(job)
        with log.open('w') as stream:process=subprocess.Popen(command,cwd=spec['cwd'],stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,env=env)
        root=psutil.Process(process.pid);paused=[];offset=0
        state=update(library,identity,status='running',progress=0,message='Building scene',attempt=attempt,log=str(log),pid=root.pid,process_created=root.create_time(),paused_processes=[])
    try:
        if root is None and state['status']=='starting':launch()
        elif root is not None and state['status']=='paused' and not paused:paused=[(p.pid,p.create_time()) for p in [root]+root.children(recursive=True)]
        while True:
            with connect(library) as db:
                db.execute('BEGIN IMMEDIATE');request=db.execute('SELECT request FROM render_jobs WHERE id=?',(identity,)).fetchone()[0]
                db.execute('UPDATE render_jobs SET request=NULL WHERE id=?',(identity,))
            root=live(state.get('pid'),state.get('process_created'))
            if request=='restart':
                if root:terminate_tree(root,paused)
                if process:process.wait(timeout=5)
                launch();continue
            if request=='stop' and root and state['status']!='paused':
                paused=suspend_tree(root);state=update(library,identity,status='paused',message='Stopped — ready to continue (memory retained)',paused_processes=paused)
            elif request=='continue' and root and state['status']=='paused':
                resume_tree(paused);paused=[];state=update(library,identity,status='running',message='Continuing render',paused_processes=[])
            if state['status']!='paused':
                offset=log_progress(state['log'],offset,state)
                state=update(library,identity,progress=state['progress'],message=state['message'])
            code=process.poll() if process else None
            if root is None or code is not None:
                if process:
                    code=process.wait();status='completed' if code==0 else 'failed';message='Render completed' if code==0 else f'Render failed (exit {code}); see log'
                elif spec['adopted']:status='finished';message='Existing render exited; check its log and output'
                else:status='interrupted';message='Render process is gone; Restart is available'
                update(library,identity,status=status,message=message,progress=100 if status=='completed' else state['progress']);return
            time.sleep(.25)
    except Exception as exc:
        update(library,identity,status='failed',message='Supervisor error: '+str(exc))
    finally:update(library,identity,supervisor_pid=None,supervisor_created=None)


def discover_running(library,project_root):
    """Attach only to owned ALICE render commands from this project, never editors."""
    import psutil
    root=Path(project_root).resolve();known=set();candidates=[]
    username=psutil.Process().username()
    for item in jobs(library):
        state=item['state']
        if live(state.get('pid'),state.get('process_created')):known.add(state['pid'])
        if (state['status'] not in TERMINAL or item['request']) and time.time()-item['spec']['created']>10 and not live(state.get('supervisor_pid'),state.get('supervisor_created')):
            start_supervisor(library,item['id'])
    for p in psutil.process_iter(['pid','cmdline','cwd','username']):
        try:
            if p.pid in known or p.username()!=username:continue
            command=p.cmdline()
            cli='alice_renderer.cli' in command and 'render-config' in command
            worker='--background' in command and '--job' in command and any(Path(v).name=='worker.py' for v in command)
            if not (cli or worker):continue
            index=command.index('render-config')+1 if cli else command.index('--job')+1
            source=Path(command[index]).resolve()
            if not source.is_relative_to(root) and Path(p.cwd()).resolve()!=root:continue
            candidates.append((not cli,p,command))
        except (psutil.Error,OSError,ValueError,IndexError):continue
    added=[]
    for worker,p,command in sorted(candidates,key=lambda c:c[0]):
        try:
            if any(a.pid in known for a in p.parents()):continue
            log=None
            if sys.platform.startswith('linux'):
                target=Path(f'/proc/{p.pid}/fd/1').resolve()
                if target.is_file():log=str(target)
            if not log and worker:log=str(Path(command[command.index('--job')+1]).parent/'blender.log')
            identity=submit(command,library=library,cwd=p.cwd(),title='Existing '+('frame render' if worker else 'render'),adopt=p,progress_log=log)
            known.add(p.pid);added.append(identity)
        except (psutil.Error,OSError,ValueError):continue
    return added


def submit_scene(blender,paths,settings,output,*,library,preview=False):
    folder=Path(library).resolve().parent/'scene-library'/'jobs'/'requests'/uuid.uuid4().hex;folder.mkdir(parents=True)
    request=folder/'request.json';request.write_text(json.dumps(dict(blender=blender,paths=[str(Path(p).resolve()) for p in paths],settings=settings.to_dict(),output=str(Path(output).resolve()),preview=preview,library=str(Path(library).resolve()))))
    return submit([sys.executable,'-m','alice_renderer.render_jobs','--scene',str(request)],library=library,title='Video' if settings.video_enabled else f'Render · {len(paths) or "geometry only"}'+(' events' if paths else ''))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--library');parser.add_argument('--run');parser.add_argument('--scene');args=parser.parse_args()
    if args.scene:
        from .runtime import render_events
        from .model import RenderSettings
        request=json.loads(Path(args.scene).read_text())
        result=render_events(request['blender'],[Path(p) for p in request['paths']],RenderSettings(**request['settings']),Path(request['output']),preview=request['preview'],library_path=request['library'],progress=lambda s:print(s,flush=True))
        print('Output: '+str(result),flush=True)
    elif args.run and args.library:supervise(args.library,args.run)
    else:parser.error('Provide --scene or --library and --run')

if __name__=='__main__':main()
