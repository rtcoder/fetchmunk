import importlib,queue,time
from pathlib import Path

def test_worker_runs_without_blocking_caller(tmp_path):
    try:m=importlib.import_module('fetchmunk_backend.supervisor')
    except ModuleNotFoundError:
        import pytest;pytest.fail('supervisor missing')
    from fetchmunk_backend.models import WorkerRequest
    events=queue.Queue();s=m.WorkerSupervisor(lambda r,e:events.put(e))
    s.start(WorkerRequest('j',1,'https://example.org/not-supported',tmp_path,tmp_path/'archive'))
    msg=events.get(timeout=10)
    assert msg['kind']=='result' and msg['data']['error_code']=='unsupported_url'
    s.join(5)
    assert not s.running
