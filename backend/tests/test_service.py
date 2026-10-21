import importlib, uuid
import pytest


class ControlledWorker:
    def __init__(self, callback):
        self.callback = callback
        self.request = None

    def start(self, request):
        self.request = request

    def stop(self, reason, grace_seconds=5):
        if self.request:
            self.callback(self.request, {"kind": "exit", "data": {}})
            self.request = None

    def finish(self, **data):
        req = self.request
        self.request = None
        self.callback(
            req,
            {
                "kind": "result",
                "data": dict(
                    downloaded=0, skipped=0, failed_files=0, error_code=None, **data
                ),
            },
        )


@pytest.fixture
def service(tmp_path):
    try:
        m = importlib.import_module("fetchmunk_backend.service")
    except ModuleNotFoundError:
        pytest.fail("job service missing")
    s = m.JobService(lambda e: None, supervisor_factory=ControlledWorker)
    call(
        s,
        "session.initialize",
        data_dir=str(tmp_path / "state"),
        default_destination=str(tmp_path / "files"),
    )
    yield s
    s.close()


def call(s, method, **params):
    params.setdefault("operation_id", str(uuid.uuid4()))
    response = s.handle(
        {
            "protocol": 1,
            "type": "request",
            "id": "r",
            "method": method,
            "params": params,
        }
    )
    assert "error" not in response, response
    return response["result"]


def add(s):
    return call(
        s,
        "jobs.create",
        url="https://example.org/a.png",
        destination=str(s.destination),
    )["job_id"]


def test_fifo_and_cancel(service):
    a = add(service)
    b = add(service)
    assert call(service, "jobs.get", job_id=a)["state"] == "extracting"
    assert call(service, "jobs.get", job_id=b)["state"] == "queued"
    call(service, "jobs.cancel", job_id=a)
    assert call(service, "jobs.get", job_id=a)["state"] == "cancelled"
    assert call(service, "jobs.get", job_id=b)["state"] == "extracting"


def test_duplicate_create_and_retry_attempt(service):
    params = dict(
        operation_id="same",
        url="https://example.org/a.png",
        destination=str(service.destination),
    )
    first = call(service, "jobs.create", **params)
    assert call(service, "jobs.create", **params) == first
    assert len(service.store.all_jobs()) == 1
    call(service, "jobs.cancel", job_id=first["job_id"])
    retried = call(service, "jobs.retry", job_id=first["job_id"])
    assert retried["attempt"] == 2
    assert service.store.db.execute("select count(*) from attempts").fetchone()[0] == 1


@pytest.mark.parametrize(
    "counts,state",
    [
        ({"downloaded": 1}, "completed"),
        ({"skipped": 1}, "completed"),
        ({}, "empty"),
        ({"downloaded": 1, "failed_files": 1, "error_code": "engine_error"}, "partial"),
        ({"error_code": "engine_error"}, "failed"),
        ({"error_code": "auth_required"}, "needs_auth"),
    ],
)
def test_result_classification(service, counts, state):
    j = add(service)
    req = service.supervisor.request
    data = dict(downloaded=0, skipped=0, failed_files=0, error_code=None)
    data.update(counts)
    service.on_worker(req, {"kind": "result", "data": data})
    assert call(service, "jobs.get", job_id=j)["state"] == state
    call(service, "jobs.cancel", job_id=j)
    assert call(service, "jobs.get", job_id=j)["state"] == (
        "cancelled" if state == "needs_auth" else state
    )


def test_stale_worker_cannot_complete_cancelled_job(service):
    j = add(service)
    old = service.supervisor.request
    call(service, "jobs.cancel", job_id=j)
    call(service, "jobs.retry", job_id=j)
    service.on_worker(old, {"kind": "result", "data": {"downloaded": 99}})
    assert call(service, "jobs.get", job_id=j)["attempt"] == 2
    assert call(service, "jobs.get", job_id=j)["state"] == "extracting"


def test_restart_requires_queue_confirmation(service):
    add(service)
    directory = service.store.data_dir
    destination = service.destination
    service.close()
    m = importlib.import_module("fetchmunk_backend.service")
    s = m.JobService(lambda e: None, supervisor_factory=ControlledWorker)
    try:
        init = call(
            s,
            "session.initialize",
            data_dir=str(directory),
            default_destination=str(destination),
        )
        assert init["queue_enabled"] is False
        assert s.store.all_jobs()[0]["state"] == "interrupted"
    finally:
        s.close()


@pytest.mark.parametrize(
    "url",
    ["file:///tmp/test", "https://user:secret@host/test", "--exec bad", "https://"],
)
def test_rejects_invalid_url(service, url):
    r = service.handle(
        {
            "id": "r",
            "method": "jobs.create",
            "params": {
                "operation_id": "x",
                "url": url,
                "destination": str(service.destination),
            },
        }
    )
    assert r["error"]["code"] == "invalid_url"


def test_large_history_summary_and_paging_do_not_load_all_jobs(service, monkeypatch):
    call(service, 'queue.set_enabled', enabled=False)
    with service.store.db:
        for i in range(1001):
            service.store.save_job(dict(job_id=str(i), state='completed', revision=1, created_at='same'),service.store.db)
    monkeypatch.setattr(service.store,'all_jobs',lambda:pytest.fail('full history read'))
    params=dict(operation_id='large',url='https://example.org/a.png',destination=str(service.destination))
    first=call(service,'jobs.create',**params)
    assert call(service,'jobs.create',**params)==first
    summary=call(service,'jobs.summary')
    assert summary['total']==1002 and summary['history']==1001 and summary['active']==1
    assert len(call(service,'jobs.snapshot',filter='history')['jobs'])==100
    call(service,'queue.set_enabled',enabled=True)
    assert call(service,'jobs.summary')['current_job']['job_id']==first['job_id']


def full_disk():
    import sqlite3
    e=sqlite3.OperationalError('simulated full disk');e.sqlite_errorcode=sqlite3.SQLITE_FULL
    return e


def test_scheduler_disk_error_keeps_committed_create_idempotent(service,monkeypatch):
    emitted=[];service.emit=emitted.append
    original=service.store.save_job
    def fail_start(job,db=None):
        if job['state']=='extracting':raise full_disk()
        return original(job,db)
    monkeypatch.setattr(service.store,'save_job',fail_start)
    params=dict(operation_id='full',url='https://example.org/a.png',destination=str(service.destination))
    first=call(service,'jobs.create',**params)
    assert call(service,'jobs.create',**params)==first
    assert service.active is None and not service.queue_enabled
    assert service.store.get_job(first['job_id'])['state']=='queued'
    assert any(e['data'].get('error',{}).get('code')=='disk_full' for e in emitted)


def test_checkpoint_failure_is_controlled_and_worker_failure_stops_queue(service,monkeypatch):
    original=service.snapshots.maintain
    def broken(store):raise OSError(28,'simulated checkpoint failure')
    monkeypatch.setattr(service.snapshots,'maintain',broken)
    result=call(service,'jobs.summary')
    assert result['total']==0
    assert not service.queue_enabled
    monkeypatch.setattr(service.snapshots,'maintain',original)
    call(service,'queue.set_enabled',enabled=True)
    jid=add(service);request=service.supervisor.request
    original_save=service.store.save_job
    monkeypatch.setattr(service.store,'save_job',lambda *a,**k:(_ for _ in ()).throw(full_disk()))
    service.on_worker(request,dict(kind='file.start',data=dict(name='a.png')))
    assert service.active is None and not service.queue_enabled
    assert service.supervisor.request is None
    monkeypatch.setattr(service.store,'save_job',original_save)
