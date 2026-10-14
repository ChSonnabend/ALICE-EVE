import importlib.util,json
from pathlib import Path
from types import SimpleNamespace
import pytest

def module():
    path=Path(__file__).resolve().parents[1]/'tools/reconstructed_input.py'
    spec=importlib.util.spec_from_file_location('reconstructed_input_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_inspection_does_not_claim_missing_clusters(tmp_path):
    m=module()
    for name in ('tpctracks.root','o2trac_its.root','unknown.root'):(tmp_path/name).touch()
    report=m.inspect(tmp_path)
    assert report['track_candidates']==['ITS','TPC']
    assert report['cluster_candidates']==[]
    assert report['missing_vertex_files']==list(m.VERTICES)
    assert report['other_root_files']==['unknown.root']


def test_actual_reader_requirements_include_companions_not_outputs(tmp_path):
    m=module()
    graph={'workflow':[
        {'name':'trd-tracklet-reader','options':[{'name':'infile','defaultValue':'trdtracklets.root'},{'name':'calibrated-infile','defaultValue':'trdcalibratedtracklets.root'}]},
        {'name':'vertex-writer','options':[{'name':'outfile','defaultValue':'new.root'}]}]}
    (tmp_path/'trdtracklets.root').touch()
    with pytest.raises(ValueError,match='trdcalibratedtracklets.root'):m.check_inputs(graph,tmp_path)
    report=json.loads((tmp_path/'input-requirements.json').read_text())
    assert len(report['missing'])==1 and len(report['requirements'])==2


def config_fixture(tmp_path):
    m=module();source=tmp_path/'input';source.mkdir()
    for name in (*m.VERTICES,'o2trac_its.root','o2clus_its.root','tfidinfo.root'):(source/name).touch()
    exporter=tmp_path/'exporter';exporter.touch()
    cfg=dict(run=1,timestamp_ms=1,first_orbit=1,orbits_per_tf=32,expected_timeframes=1,condition_backend='http://example.invalid',
             exporter=str(exporter),inventory=str(exporter),timing_file='tfidinfo.root',
             track_sources='ITS',cluster_sources='ITS',vertexing_sources='ITS')
    config=tmp_path/'config.json';config.write_text(json.dumps(cfg))
    return m,SimpleNamespace(input=source,config=config,work=tmp_path/'work',vertices='reuse',execute=False)


def test_prepare_rebuild_preserves_originals_and_requires_explicit_sources(tmp_path):
    m,args=config_fixture(tmp_path);args.vertices='rebuild';calls=[]
    def run(tool,*values):
        calls.append((tool,*values))
        if tool=='run_o2_workflow.py':
            stage=values[0]
            names=['o2trac_its.root'] if stage.name=='vertexing' else ['o2clus_its.root',*m.VERTICES]
            graph={'workflow':[{'name':'root-reader','options':[{'name':'infile','defaultValue':n} for n in names]}]}
            (stage/'workflow.json').write_text(json.dumps(graph))
    m.process(args,run)
    assert len(calls)==2 and all(c[-1]=='--dump' for c in calls)
    assert not (args.work/'vertexing'/m.VERTICES[0]).exists()
    assert (args.input/m.VERTICES[0]).exists()
    assert (args.work/'exporting'/m.VERTICES[0]).is_symlink()
    assert (args.work/'exporting'/m.VERTICES[0]).readlink()==args.work/'vertexing'/m.VERTICES[0]
    assert not (args.work/'export/manifest.json').exists()
    command=(args.work/'vertexing/reconstruct.sh').read_text()
    assert '--vertexing-sources ITS' in command and '--vertex-track-matching-sources ITS' in command


def test_missing_vertices_and_timing_fail_before_execution(tmp_path):
    m,args=config_fixture(tmp_path)
    (args.input/m.VERTICES[0]).unlink()
    with pytest.raises(ValueError,match='Reuse needs'):m.process(args,lambda *a:pytest.fail('Unexpected execution'))


def test_explicit_filename_alias_is_staged_without_renaming_input(tmp_path):
    m,args=config_fixture(tmp_path)
    (args.input/'o2clus_its.root').rename(args.input/'custom-clusters.root')
    cfg=json.loads(args.config.read_text());cfg['input_files']={'o2clus_its.root':'custom-clusters.root'}
    args.config.write_text(json.dumps(cfg))
    def run(tool,*values):(values[0]/'workflow.json').write_text(json.dumps({'workflow':[]}))
    m.process(args,run)
    assert (args.work/'exporting/o2clus_its.root').resolve()==args.input/'custom-clusters.root'
    assert not (args.input/'o2clus_its.root').exists()


def test_combined_vertex_reader_does_not_require_obsolete_match_file(tmp_path):
    m=module();(tmp_path/'o2_primary_vertex.root').touch()
    graph={'workflow':[{'name':'primary-vertex-reader','options':[
        {'name':'primary-vertex-infile','defaultValue':'o2_primary_vertex.root'},
        {'name':'vertex-track-matches-infile','defaultValue':'o2_pvertex_track_matches.root'}]}]}
    assert len(m.check_inputs(graph,tmp_path)['requirements'])==1
