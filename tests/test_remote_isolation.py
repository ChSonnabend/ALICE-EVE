import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('o2_remote_exec',Path(__file__).parents[1]/'tools/o2_remote_exec.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@pytest.mark.parametrize('step',['0','00','batch','extern','-1',''])
def test_original_or_invalid_step_is_never_cancelled(step):
    assert module.cancellable_step({'job':16999956,'step':step,'request':'request-test.json'},'16999956','request-test.json') is None

def test_only_matching_request_and_job_can_cancel():
    item={'job':16999956,'step':'2','request':'request-test.json'}
    assert module.cancellable_step(item,'16999956','request-test.json')=='16999956.2'
    assert module.cancellable_step(item,'16999957','request-test.json') is None
    assert module.cancellable_step(item,'16999956','request-other.json') is None
