import pytest
from test_service import service, call
from fetchmunk_backend.wire import encode_frame, FrameDecoder


def batch(s, urls, operation_id='batch', destination=None):
    return s.handle(dict(id='b', method='jobs.create_many', params=dict(
        operation_id=operation_id, urls=urls,
        destination=destination if destination is not None else str(s.destination))))


def test_batch_deduplicates_exact_strings_and_runs_fifo_after_commit(service):
    seen = []
    def emit(event):
        assert not service.store.db.in_transaction
        assert service.store.summary()['total'] == 3
        seen.append(event)
    service.emit = emit
    urls = ['https://example.org/b?q=1', 'https://example.org/a',
            'https://example.org/b?q=1', 'https://example.org/b?q=2']
    result = batch(service, urls)['result']
    assert result['created_count'] == 3 and result['duplicate_count'] == 1
    jobs = service.store.all_jobs()
    assert [j['url'] for j in jobs] == [urls[0], urls[1], urls[3]]
    assert [j['job_id'] for j in jobs] == [j['job_id'] for j in result['jobs']]
    assert [j['revision'] for j in result['jobs']] == [1, 1, 1]
    assert len({j['output_dir'] for j in jobs}) == 3
    assert service.supervisor.request.job_id == jobs[0]['job_id']
    service.supervisor.finish()
    assert service.supervisor.request.job_id == jobs[1]['job_id']
    service.supervisor.finish()
    assert service.supervisor.request.job_id == jobs[2]['job_id']
    service.emit = lambda e: None


def test_replayed_batch_has_no_duplicate_events_or_jobs(service):
    events = []
    service.emit = events.append
    urls = ['https://example.org/a', 'https://example.org/b']
    first = batch(service, urls)
    assert 'result' in first
    count = len(events)
    assert batch(service, urls) == first
    assert len(events) == count
    assert service.store.summary()['total'] == 2
    assert batch(service, urls[::-1])['error']['code'] == 'operation_conflict'
    assert batch(service, urls, destination='/tmp/other')['error']['code'] == 'operation_conflict'


@pytest.mark.parametrize('urls', [None, 'https://example.org', {}, [], ['https://example.org'] * 101])
def test_rejects_invalid_batch_shape(service, urls):
    assert batch(service, urls)['error']['code'] == 'invalid_params'
    assert service.store.summary()['total'] == 0


@pytest.mark.parametrize('url', [None, 12, True, {}, [], '', 'file:///a', 'https://',
    ' https://example.org', 'https://example.org/a b', 'https://example.org/\n',
    'https://example.org/\x00', 'https://example.org/\x01', 'https://example.org/\x7f',
    'https://example.org/\x85', 'https://@example.org', 'https://user@example.org',
    'https://:pass@example.org', 'https://example.org:65536', 'https://example.org:no',
    'https://example.org/' + 'a' * 16384])
@pytest.mark.parametrize('method', ['jobs.create', 'jobs.create_many'])
def test_common_url_validation_is_atomic(service, url, method):
    if method == 'jobs.create_many':
        result = batch(service, ['https://example.org/valid', url])
    else:
        result = service.handle(dict(id='r', method=method, params=dict(
            operation_id='single', url=url, destination=str(service.destination))))
    assert result['error']['code'] == 'invalid_url'
    assert service.store.summary()['total'] == 0
    assert service.supervisor.request is None


def test_batch_byte_limit_counts_utf8_and_duplicates(service):
    # Each URL fits the character limit, but the repeated input exceeds 512 KiB.
    url = 'https://example.org/' + '\u00e9' * 9000
    assert batch(service, [url] * 30)['error']['code'] == 'invalid_params'
    assert service.store.summary()['total'] == 0


def test_maximum_count_and_character_length_roundtrip(service):
    call(service, 'queue.set_enabled', enabled=False)
    urls = ['https://example.org/' + str(i) for i in range(100)]
    urls[0] = 'https://example.org/' + 'a' * (16384 - len('https://example.org/'))
    request = dict(protocol=1, type='request', id='x', method='jobs.create_many', params=dict(
        operation_id='frame', urls=urls, destination=str(service.destination)))
    decoded = FrameDecoder().feed(encode_frame(request))[0]
    result = service.handle(decoded)['result']
    assert result['created_count'] == 100


def test_database_failure_rolls_back_entire_batch_and_operation(service):
    events = []
    service.emit = events.append
    service.store.db.execute("""CREATE TRIGGER fail_second BEFORE INSERT ON jobs
        WHEN json_extract(new.data, '$.url') = 'https://example.org/fail'
        BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
    result = batch(service, ['https://example.org/ok', 'https://example.org/fail'])
    assert result['error']['code'] == 'database_error'
    assert service.store.summary()['total'] == 0
    assert service.store.db.execute('SELECT count(*) FROM operations').fetchone()[0] == 0
    assert events == []
    assert service.supervisor.request is None
    service.store.db.execute('DROP TRIGGER fail_second')
    assert batch(service, ['https://example.org/ok', 'https://example.org/fail'])['result']['created_count'] == 2


def test_invalid_destination_has_no_partial_batch(service):
    assert batch(service, ['https://example.org'], destination='relative')['error']['code'] == 'invalid_params'
    assert service.store.summary()['total'] == 0


def test_total_byte_boundary_and_frame_roundtrip(service):
    call(service, 'queue.set_enabled', enabled=False)
    prefix = 'https://example.org/'
    url = prefix + 'a' * (16384 - len(prefix))
    request = dict(protocol=1, type='request', id='limit', method='jobs.create_many', params=dict(
        operation_id='byte-limit', urls=[url] * 32, destination=str(service.destination)))
    decoded = FrameDecoder().feed(encode_frame(request))[0]
    result = service.handle(decoded)['result']
    assert result['created_count'] == 1 and result['duplicate_count'] == 31
    assert batch(service, [url] * 32 + [prefix], operation_id='too-large')['error']['code'] == 'invalid_params'
    assert service.store.summary()['total'] == 1


def test_committed_batch_replays_after_service_restart(service):
    from fetchmunk_backend.service import JobService
    from test_service import ControlledWorker
    urls = ['https://example.org/a', 'https://example.org/b']
    first = batch(service, urls)
    assert 'result' in first
    directory, destination = service.store.data_dir, service.destination
    service.close()
    events = []
    restarted = JobService(events.append, supervisor_factory=ControlledWorker)
    try:
        call(restarted, 'session.initialize', data_dir=str(directory), default_destination=str(destination))
        assert batch(restarted, urls) == first
        assert restarted.store.summary()['total'] == 2
        assert restarted.supervisor.request is None
        assert events == []
    finally:
        restarted.close()
