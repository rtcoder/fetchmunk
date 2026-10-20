import importlib
import pytest

def api():
    try:return importlib.import_module('fetchmunk_backend.snapshots')
    except ModuleNotFoundError:pytest.fail('snapshots missing')

def test_snapshot_consistent_paginated_and_expires():
    m=api();clock=[0];s=m.SnapshotStore(clock=lambda:clock[0])
    jobs=[{'job_id':str(i),'revision':1} for i in range(102)]
    first=s.create(jobs,9,limit=100)
    jobs[-1]['revision']=22
    second=s.page(first['next_cursor'],100)
    assert len(first['jobs'])==100
    assert second['jobs'][-1]['revision']==1 and second['at_seq']==9
    clock[0]=61
    with pytest.raises(m.SnapshotError,match='snapshot_expired'):s.page(first['next_cursor'],100)

def test_byte_limit():
    m=api();s=m.SnapshotStore()
    result=s.create([{'job_id':str(i),'data':'x'*300000} for i in range(10)],0,100)
    assert len(result['jobs'])==3
    assert result['next_cursor']
