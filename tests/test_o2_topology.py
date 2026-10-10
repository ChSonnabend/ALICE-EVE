import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('run_o2_workflow',Path(__file__).parents[1]/'tools/run_o2_workflow.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def device(name,ipcid=None):
    args=['--session','alice-test','--shm-segment-id','12000']
    if ipcid is not None:args+=['--timeframes-rate-limit-ipcid',str(ipcid)]
    return dict(name=name,cmdLineArgs=args)

def test_missing_flow_control_rejected_before_device_connections():
    with pytest.raises(ValueError,match='timeframes-rate-limit-ipcid'):
        module.validate_common_options(dict(metadata=[device('reconstruction',0),device('exporter')]))

def test_consistent_flow_control_and_separate_shm_session():
    module.validate_common_options(dict(metadata=[device('reconstruction',0),device('exporter',0),device('inventory',0)]))
    bad=device('inventory',0);bad['cmdLineArgs'][1]='other'
    with pytest.raises(ValueError,match='session'):
        module.validate_common_options(dict(metadata=[device('reconstruction',0),bad]))

def test_private_socket_namespaces_differ_in_same_allocation(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    spec=importlib.util.spec_from_file_location('workflow_driver',Path(__file__).parents[1]/'tools/o2_workflow_driver.py')
    driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    root=tmp_path/'O2';script=root/'prodtests/full-system-test/dpl-workflow.sh'
    script.parent.mkdir(parents=True);script.write_text('if [[ $EPNSYNCMODE == 0 && ${DPL_CONDITION_BACKEND:-}')
    field=root/'share/Common/maps/mfchebKGI_sym.root';field.parent.mkdir(parents=True);field.write_bytes(b'fixture')
    source=tmp_path/'arbitrary.root';source.write_bytes(b'fixture')
    monkeypatch.setenv('O2_ROOT',str(root));monkeypatch.setenv('VMCWORKDIR',str(root/'share'))
    monkeypatch.setenv('SLURM_JOB_ID','16999956');monkeypatch.delenv('ALIEN_PROC_ID',raising=False)
    monkeypatch.setattr(driver.subprocess,'run',lambda *args,**kw:SimpleNamespace(returncode=0,stdout='#Workflow command:\no2-reader',stderr=''))
    cfg=dict(input=str(source),format='ctf',detectors=['ITS','TPC'],beam_type='PbPb',orbits_per_tf=32,condition_backend='http://ccdb')
    namespaces=[]
    for name in ('first','second'):
        folder=tmp_path/name;driver.generate(cfg,folder)
        env=json.loads((folder/'workflow-environment.json').read_text())
        namespaces.append(env['ALIEN_PROC_ID'])
        assert env['ALIEN_PROC_ID']==env['OVERRIDE_SESSION']
        assert '--ctf-file-regex' in env['ARGS_EXTRA_PROCESS_o2_ctf_reader_workflow']
    assert namespaces[0]!=namespaces[1]
    assert driver.os.environ['SLURM_JOB_ID']=='16999956'
