import json
import pytest
from alice_renderer.enumeration import reconcile_export


def fixture(tmp_path):
    inventory=tmp_path/'pv-inventory.jsonl';events=tmp_path/'events.jsonl'
    rows=[dict(schema_version=1,run=560067,tf_counter=42+i,orbit=100+32*i,
               vertex_count=count,vertices=[dict(index=j,position_cm=[0,0,j]) for j in range(count)]) for i,count in enumerate((31,0))]
    inventory.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    (tmp_path/'pv-inventory.jsonl.complete.json').write_text(json.dumps(dict(schema_version=1,timeframes=2,vertices=31)))
    items=[dict(schema_version=1,kind='collision',units='cm',id=f'pv-{i}',run=560067,timeframe=42,orbit=100,
                primary_vertex=i,vertex=[0,0,i],tracks=[],clusters=[]) for i in range(31)]
    events.write_text(''.join(json.dumps(x)+'\n' for x in items))
    return events,inventory,items


def test_empty_vertices_and_timeframes_are_retained(tmp_path):
    events,inventory,_=fixture(tmp_path)
    result=reconcile_export(events,inventory,expected_timeframes=2,expected_identities={(560067,42,100),(560067,43,132)})
    assert result['event_count']==31 and result['timeframes_processed']==2


@pytest.mark.parametrize('mutation,match',[
    ('missing','omitted'),('duplicate','more than once'),('extra','absent'),
    ('id','Duplicate event identifier'),('vertex','coordinates differ')])
def test_lost_duplicate_or_wrong_events_are_rejected(tmp_path,mutation,match):
    events,inventory,items=fixture(tmp_path)
    if mutation=='missing':items.pop()
    elif mutation=='duplicate':items.append(items[0])
    elif mutation=='extra':items[0]['primary_vertex']=31
    elif mutation=='id':items[1]['id']=items[0]['id']
    elif mutation=='vertex':items[0]['vertex']=[1,0,0]
    events.write_text(''.join(json.dumps(x)+'\n' for x in items))
    with pytest.raises(ValueError,match=match):reconcile_export(events,inventory,expected_timeframes=2)


def test_omitted_timeframe_and_incomplete_inventory(tmp_path):
    events,inventory,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='Processed'):reconcile_export(events,inventory,expected_timeframes=3)
    inventory.write_text(inventory.read_text().splitlines()[0]+'\n')
    with pytest.raises(ValueError,match='Processed'):reconcile_export(events,inventory,expected_timeframes=2)
