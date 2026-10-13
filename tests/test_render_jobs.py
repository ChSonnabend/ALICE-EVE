"""Exercise detached supervision with real processes, including child processes."""
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest
from alice_renderer import render_jobs as r


def until(check, timeout=15):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=check()
        if result:return result
        time.sleep(.05)
    raise AssertionError('Timed out waiting for render job')


@pytest.fixture
def registry(tmp_path):
    library=tmp_path/'library.sqlite'
    yield library
    for item in r.jobs(library):
        state=item['state']
        root=r.live(state.get('pid'),state.get('process_created'))
        if root:r.terminate_tree(root)
        supervisor=r.live(state.get('supervisor_pid'),state.get('supervisor_created'))
        if supervisor:supervisor.kill()


def test_detached_pause_continue_restart_with_child(registry,tmp_path):
    script=tmp_path/'render.py'
    script.write_text("""
import subprocess,sys,time
from pathlib import Path
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
Path(sys.argv[1]).write_text(str(child.pid))
print('Render progress: 25%',flush=True)
while not Path(sys.argv[2]).exists():time.sleep(.03)
child.terminate();child.wait()
print('Render progress: 100%',flush=True)
""")
    pidfile=tmp_path/'child.pid';finish=tmp_path/'finish'
    # Launch from a short-lived client: the job must outlive its submitter.
    client=subprocess.run([sys.executable,'-c',
        'from alice_renderer.render_jobs import submit; import sys; print(submit([sys.executable,*sys.argv[2:]],library=sys.argv[1]))',
        str(registry),str(script),str(pidfile),str(finish)],capture_output=True,text=True,check=True)
    identity=client.stdout.strip()
    state=lambda:r.get(registry,identity)['state']
    until(lambda:state()['progress']==25 and pidfile.exists())
    initial=state()['pid'];created=state()['process_created'];child=psutil.Process(int(pidfile.read_text()))
    r.control(registry,identity,'stop')
    until(lambda:state()['status']=='paused')
    assert psutil.Process(initial).status()==psutil.STATUS_STOPPED
    assert child.status()==psutil.STATUS_STOPPED
    r.control(registry,identity,'continue')
    until(lambda:state()['status']=='running')
    assert child.status()!=psutil.STATUS_STOPPED
    r.control(registry,identity,'restart')
    until(lambda:state()['attempt']==2 and state()['progress']==25)
    assert state()['pid']!=initial
    assert not r.live(initial,created)
    assert Path(state()['log']).name=='attempt-2.log'
    assert (Path(state()['log']).parent/'attempt-1.log').exists()
    finish.touch()
    until(lambda:state()['status']=='completed')
    assert state()['progress']==100


def test_adopt_and_pause_existing_process(registry,tmp_path):
    p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
    try:
        identity=r.submit(p.args,library=registry,adopt=psutil.Process(p.pid))
        until(lambda:r.get(registry,identity)['state'].get('supervisor_pid'))
        r.control(registry,identity,'stop')
        until(lambda:r.get(registry,identity)['state']['status']=='paused')
        assert psutil.Process(p.pid).status()==psutil.STATUS_STOPPED
        r.control(registry,identity,'continue')
        until(lambda:r.get(registry,identity)['state']['status']=='running')
        p.terminate();p.wait()
        until(lambda:r.get(registry,identity)['state']['status']=='finished')
        assert r.get(registry,identity)['state']['progress']<100
    finally:
        if p.poll() is None:p.kill();p.wait()


def test_failed_job_can_restart(registry):
    identity=r.submit([sys.executable,'-c','raise SystemExit(7)'],library=registry)
    until(lambda:r.get(registry,identity)['state']['status']=='failed')
    assert r.get(registry,identity)['state']['progress']<100
    r.control(registry,identity,'restart')
    until(lambda:r.get(registry,identity)['state']['attempt']==2 and r.get(registry,identity)['state']['status']=='failed')


def test_raw_worker_restart_preserves_output(registry,tmp_path):
    original=tmp_path/'original';original.mkdir()
    (original/'render.png').write_text('keep me')
    job=original/'job.json';job.write_text(json.dumps({'output':str(original)}))
    worker=tmp_path/'worker.py'
    worker.write_text("import json,sys; from pathlib import Path; p=json.loads(Path(sys.argv[-1]).read_text()); (Path(p['output'])/'render.png').write_text('new attempt')")
    identity=r.submit([sys.executable,str(worker),'--job',str(job)],library=registry)
    until(lambda:r.get(registry,identity)['state']['status']=='completed')
    assert (original/'render.png').read_text()=='keep me'
    folder=Path(r.get(registry,identity)['spec']['folder'])
    assert (folder/'attempt-1'/'render.png').read_text()=='new attempt'


def test_pid_identity_and_progress(tmp_path):
    me=psutil.Process()
    assert r.live(me.pid,me.create_time()+10) is None
    log=tmp_path/'log';log.write_text('Render progress: 20%\nALICE_FRAME 3/10\n')
    state={'progress':0}
    offset=r.log_progress(log,0,state);assert state['progress']==30
    with log.open('a') as out:out.write('Render progress: 100%\n')
    r.log_progress(log,offset,state);assert state['progress']==99


def test_discovery_skips_interactive_and_child_worker(registry,tmp_path,monkeypatch):
    from types import SimpleNamespace
    username=psutil.Process().username()
    cli=['python','-m','alice_renderer.cli','render-config',str(tmp_path/'scene.json')]
    worker=['blender','--background','--python','worker.py','--','--job',str(tmp_path/'job.json')]
    editor=['blender','--python','worker.py','--','--job',str(tmp_path/'job.json'),'--interactive']
    def fake(pid,command,parents=()):
        return SimpleNamespace(pid=pid,cmdline=lambda:command,cwd=lambda:str(tmp_path),username=lambda:username,parents=lambda:list(parents))
    parent=fake(99999991,cli)
    child=fake(99999992,worker,[parent])
    interactive=fake(99999993,editor)
    monkeypatch.setattr(psutil,'process_iter',lambda *args:[child,interactive,parent])
    captured=[]
    def submit(command,**kwargs):captured.append(kwargs['adopt'].pid);return 'adopted'
    monkeypatch.setattr(r,'submit',submit)
    assert r.discover_running(registry,tmp_path)==['adopted']
    assert captured==[99999991]
