import json
from alice_renderer.timeframe_views import export_views
from alice_renderer.catalogue import iter_json
from alice_renderer.model import validate_event,capabilities

def test_whole_tf_views_preserve_grouping_and_flag_invalid_coordinates(tmp_path):
    records=[]
    for tf in (1,2):
        records.append(dict(schema_version=1,units='cm',kind='timeframe_objects',run=560067,timeframe=tf,orbit=tf*32,spatial_objects=[dict(detector='HMP',index=0,position=[1,2,3],coordinate_basis='aligned transform'),dict(detector='HMP',index=1,position=[None,None,None],coordinate_status='nonfinite_conversion_not_renderable')],tpc_native_clusters=[dict(pad=2,time_bins=3,q_tot=4)]))
    source=tmp_path/'objects.jsonl';source.write_text('\n'.join(map(json.dumps,records)))
    output=tmp_path/'views.jsonl.gz';report=export_views(source,output)
    events=[validate_event(e) for e in iter_json(output)]
    assert report['timeframes']==2 and report['views']==2
    assert {e['timeframe'] for e in events}=={1,2}
    assert all(e['kind']=='timeframe' and len(e['clusters'])==1 and not e['tracks'] for e in events)
    assert all(e['unrendered_spatial_count']==1 for e in events)
    assert all('pt' not in capabilities(e['clusters']) and 'dca' not in capabilities(e['clusters']) for e in events)
