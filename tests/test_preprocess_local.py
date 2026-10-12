import importlib.util
from pathlib import Path
import pytest


def load():
    path=Path(__file__).resolve().parents[1]/'tools/preprocess_local.py'
    spec=importlib.util.spec_from_file_location('preprocess_local_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_ao2d_forwards_multiple_runs_and_adjacent_sidecar(tmp_path,monkeypatch):
    m=load();source=tmp_path/'AO2D.root';source.touch();calls=[]
    monkeypatch.setenv('O2_ROOT',str(tmp_path));monkeypatch.setattr(m,'run',lambda *a:calls.append(a))
    monkeypatch.setattr(m.sys,'argv',['preprocess_local.py','ao2d','--input',str(source),'--runs','1','2','--cache',str(tmp_path/'cache')])
    m.main()
    assert calls==[('ao2d_field_conditions.py','--runs',1,2,'--cache',tmp_path/'cache','--output',str(source)+'.renderer.json')]


def test_build_does_not_replace_existing_exporter_source(tmp_path,monkeypatch):
    m=load();(tmp_path/'exporter-source').mkdir();monkeypatch.setenv('O2_ROOT',str(tmp_path))
    monkeypatch.setattr(m.sys,'argv',['preprocess_local.py','build','--o2-source',str(tmp_path),'--work',str(tmp_path)])
    with pytest.raises(SystemExit):m.main()
