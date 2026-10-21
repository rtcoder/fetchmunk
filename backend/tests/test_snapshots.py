import pytest
from fetchmunk_backend.store import JobStore
from fetchmunk_backend.snapshots import SnapshotStore, SnapshotError


@pytest.fixture
def store(tmp_path):
    s=JobStore.open(tmp_path)
    yield s
    s.close()


def seed(store,n=205,padding=0):
    with store.db:
        for i in range(n):
            store.save_job(dict(job_id=f'{i:06d}',state='completed',revision=1,created_at='same',data='x'*padding),store.db)


def ids(page):return [j['job_id'] for j in page['jobs']]


def test_stable_keyset_forward_reverse_and_expiration(store):
    seed(store)
    clock=[0];s=SnapshotStore(clock=lambda:clock[0])
    try:
        a=s.create(store,9)
        assert ids(a)==[f'{i:06d}' for i in range(204,104,-1)]
        store.save_job(dict(job_id='000100',state='queued',revision=2,created_at='same'))
        b=s.page(a['next_cursor'])
        assert b['jobs'][4]['revision']==1
        assert ids(s.page(b['previous_cursor']))==ids(a)
        c=s.page(b['next_cursor'])
        assert ids(c)==['000004','000003','000002','000001','000000']
        assert c['next_cursor'] is None
        assert s.page(c['previous_cursor'])['at_seq']==9
        clock[0]=61
        with pytest.raises(SnapshotError,match='snapshot_expired'):s.page(a['next_cursor'])
    finally:s.close()


def test_byte_limited_reverse_has_no_gaps(store):
    seed(store,10,300000);s=SnapshotStore()
    try:
        pages=[];p=s.create(store,0)
        while True:
            pages+=ids(p)
            if not p['next_cursor']:break
            p=s.page(p['next_cursor'])
        assert pages==[f'{i:06d}' for i in range(9,-1,-1)]
        backwards=ids(p)
        while p['previous_cursor']:
            p=s.page(p['previous_cursor'])
            backwards=ids(p)+backwards
        assert backwards==pages
    finally:s.close()


def test_filter_validation_eviction_and_wal_budget(store):
    seed(store);s=SnapshotStore(wal_budget=1)
    try:
        a=s.create(store,0,filter='history')
        with pytest.raises(SnapshotError,match='invalid_params'):s.page(a['next_cursor'],filter='active')
        with pytest.raises(SnapshotError):s.page(a['next_cursor']+'tampered')
        for _ in range(4):s.create(store,0)
        with pytest.raises(SnapshotError,match='snapshot_expired'):s.page(a['next_cursor'])
        b=s.create(store,1)
        store.save_job(dict(job_id='new',state='queued',revision=1,created_at='z'))
        s.maintain(store)
        with pytest.raises(SnapshotError,match='snapshot_expired'):s.page(b['next_cursor'])
        assert not s.snapshots
    finally:s.close()


def test_anchor_refresh_and_empty_filter(store):
    seed(store);s=SnapshotStore()
    try:
        assert s.create(store,0,filter='active')['jobs']==[]
        a=s.create(store,0,anchor=['same','000100'])
        assert a['jobs'][0]['job_id']=='000100'
        assert a['previous_cursor']
        for bad in (0,101,True):
            with pytest.raises(SnapshotError,match='invalid_params'):s.create(store,0,limit=bad)
        with pytest.raises(SnapshotError,match='invalid_params'):s.create(store,0,filter='oops')
    finally:s.close()


def test_empty_anchor_refresh_still_allows_newer_navigation(store):
    seed(store,1);s=SnapshotStore()
    try:
        page=s.create(store,0,anchor=['before','gone'])
        assert page['jobs']==[]
        assert page['previous_cursor'] is not None
        assert ids(s.page(page['previous_cursor']))==['000000']
    finally:s.close()
