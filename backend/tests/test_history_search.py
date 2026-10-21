import pytest
from fetchmunk_backend.snapshots import SnapshotStore, SnapshotError
from fetchmunk_backend.store import JobStore
from test_service import service, call


@pytest.fixture
def history(tmp_path):
    store = JobStore.open(tmp_path)
    snapshots = SnapshotStore()
    yield store, snapshots
    snapshots.close()
    store.close()


def save(store, jid, state='completed', display_url='https://example.org/plain', output_dir='/files/plain'):
    store.save_job(dict(job_id=jid, state=state, revision=1, created_at='same',
                        display_url=display_url, output_dir=output_dir,
                        url='https://example.org/?secret=unsearchable'))


def ids(page):
    return [job['job_id'] for job in page['jobs']]


@pytest.mark.parametrize('filter,expected', [
    ('completed', ['0']), ('failed', ['4','3','2','1']), ('cancelled', ['5']),
    ('active', ['7','4']), ('history', ['6','5','3','2','1','0']),
])
def test_filter_state_membership(history, filter, expected):
    store, snapshots = history
    for i, state in enumerate(['completed','failed','partial','interrupted','needs_auth','cancelled','empty','queued']):
        save(store, str(i), state)
    assert ids(snapshots.create(store, 0, filter=filter)) == expected
    assert store.summary() == dict(total=8, active=2, history=6, completed=1, failed=4, cancelled=1)


@pytest.mark.parametrize('query,expected', [
    ('%', ['percent']), ('_', ['under']), ("'", ['quote']),
    ("' OR 1=1 --", []), ('żÓŁĆ', ['unicode']), ('STRASSE', ['german']),
    ('OuTpUt', ['path']), ('unsearchable', []), ('missing', []),
])
def test_literal_unicode_search_only_public_fields(history, query, expected):
    store, snapshots = history
    for jid, value in [('percent','100%'),('under','a_b'),('quote',"it's"),
                       ('unicode','Żółć'),('german','Straße')]:
        save(store, jid, display_url='https://example.org/'+value)
    save(store, 'path', output_dir='/files/output')
    page = snapshots.create(store, 0, query=query)
    assert ids(page) == expected
    if not expected:
        assert page['next_cursor'] is None and page['previous_cursor'] is None


@pytest.mark.parametrize('bad', [None, 1, True, [], {}, 'a'*201, 'a\0b'])
def test_query_validation(history, bad):
    store, snapshots = history
    save(store, '1'); save(store, '2')
    with pytest.raises(SnapshotError, match='invalid_params'):
        snapshots.create(store, 0, query=bad)
    cursor = snapshots.create(store, 0, limit=1)['next_cursor']
    with pytest.raises(SnapshotError, match='invalid_params'):
        snapshots.page(cursor, query=bad)


def test_query_limits_empty_and_stable_bidirectional_pages(history):
    store, snapshots = history
    for i in range(205):
        save(store, f'{i:03d}', display_url='https://example.org/Needle')
    first = snapshots.create(store, 42, query='needle')
    assert len(first['jobs']) == 100
    save(store, '100', state='failed', display_url='https://example.org/changed')
    save(store, '999', display_url='https://example.org/needle')
    second = snapshots.page(first['next_cursor'], query='needle', filter='all')
    assert ids(second) == [f'{i:03d}' for i in range(104,4,-1)]
    assert second['jobs'][4]['state'] == 'completed'
    assert ids(snapshots.page(second['previous_cursor'])) == ids(first)
    third = snapshots.page(second['next_cursor'])
    assert ids(third) == ['004','003','002','001','000']
    assert third['next_cursor'] is None and third['at_seq'] == 42
    for query in ('', 'NEEDLE', 'changed'):
        with pytest.raises(SnapshotError, match='invalid_params'):
            snapshots.page(first['next_cursor'], query=query)
    with pytest.raises(SnapshotError, match='invalid_params'):
        snapshots.page(first['next_cursor'], filter='completed', query='needle')
    assert len(snapshots.create(store, 43, query='')['jobs']) == 100
    assert snapshots.create(store, 43, query='x'*200)['jobs'] == []
    for limit in (0, 101, True):
        with pytest.raises(SnapshotError, match='invalid_params'):
            snapshots.create(store, 43, query='needle', limit=limit)


def test_ipc_search_filters_counts_and_validation(service):
    call(service, 'queue.set_enabled', enabled=False)
    for i, state in enumerate(['completed','failed','partial','interrupted','needs_auth','cancelled']):
        save(service.store, str(i), state, display_url='https://example.org/Needle')
    page = call(service, 'jobs.snapshot', filter='failed', query='needle', limit=2)
    assert ids(page) == ['4','3']
    assert ids(call(service, 'jobs.snapshot', cursor=page['next_cursor'])) == ['2','1']
    assert ids(call(service, 'jobs.snapshot', filter='completed', query='needle')) == ['0']
    assert ids(call(service, 'jobs.snapshot', filter='cancelled', query='needle')) == ['5']
    assert call(service, 'jobs.snapshot', query='absent')['jobs'] == []
    summary = call(service, 'jobs.summary')
    assert summary['failed'] == 4 and summary['cancelled'] == 1 and summary['total'] == 6
    for params in ({'query': None}, {'query': 'x'*201}, {'query': 'a\0b'},
                   {'cursor':page['next_cursor'], 'query':''},
                   {'cursor':page['next_cursor'], 'filter':'all'}):
        response = service.handle(dict(id='bad', method='jobs.snapshot', params=params))
        assert response['error']['code'] == 'invalid_params'


def test_search_over_real_jsonl_process(tmp_path):
    from test_process_lifecycle import Client
    store = JobStore.open(tmp_path / 'state')
    for i, state in enumerate(['completed','failed','partial','interrupted','needs_auth','cancelled']):
        save(store, str(i), state, display_url='https://example.org/Żółć_%')
    store.close()
    client = Client(tmp_path)
    try:
        first = client.call('jobs.snapshot', filter='failed', query='żÓŁĆ_%', limit=2)
        assert ids(first) == ['4','3']
        second = client.call('jobs.snapshot', cursor=first['next_cursor'], query='żÓŁĆ_%')
        assert ids(second) == ['2','1']
        assert ids(client.call('jobs.snapshot', cursor=second['previous_cursor'], limit=2)) == ['4','3']
        assert ids(client.call('jobs.snapshot', filter='completed', query='%')) == ['0']
        assert ids(client.call('jobs.snapshot', filter='cancelled', query='_')) == ['5']
        summary = client.call('jobs.summary')
        assert summary['failed'] == 4 and summary['cancelled'] == 1
        client.call('app.shutdown')
        assert client.p.wait(timeout=10) == 0
        assert client.p.stderr.read() == ''
    finally:
        client.cleanup()


@pytest.mark.parametrize('filter', ['completed', 'failed', 'cancelled'])
def test_state_filter_pages_do_not_sort_history_in_temp_btree(history, filter):
    store, snapshots = history
    for i in range(3):
        save(store, str(i), state=filter)
    first = snapshots.create(store, 0, filter=filter, limit=1)
    reader = snapshots.snapshots[first['snapshot_id']].db
    statements = []
    reader.set_trace_callback(statements.append)
    second = snapshots.page(first['next_cursor'], limit=1)
    snapshots.page(second['previous_cursor'], limit=1)
    reader.set_trace_callback(None)
    queries = [sql for sql in statements if sql.startswith('SELECT data,')]
    assert len(queries) == 2
    for sql in queries:
        plan = [row[3] for row in reader.execute('EXPLAIN QUERY PLAN '+sql)]
        assert not any('TEMP B-TREE' in detail for detail in plan), plan
