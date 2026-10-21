import pytest
from gallery_dl import exception
from gallery_dl.extractor.directlink import DirectlinkExtractor
from requests import Response

from fetchmunk_backend.engine import run_download
from fetchmunk_backend.models import WorkerRequest


def http_error(status):
    response = Response()
    response.status_code = status
    response.url = 'https://private.example/secret?token=secret'
    return exception.HttpError(response=response)


@pytest.mark.parametrize('error,code', [
    (exception.AuthenticationError('secret password'), 'auth_required'),
    (exception.AuthRequired('secret cookie'), 'auth_required'),
    (exception.AuthorizationError('private resource'), 'access_denied'),
    (http_error(403), 'access_denied'),
    (http_error(500), 'network_error'),
    (RuntimeError('authentication required secret'), 'engine_error'),
])
def test_typed_extractor_errors_survive_job_run(monkeypatch, tmp_path, capsys, caplog, error, code):
    def fail(self):
        raise error
        yield
    monkeypatch.setattr(DirectlinkExtractor, 'items', fail)
    events = []
    req = WorkerRequest('test', 1, 'https://example.org/photo.png', tmp_path/'files', tmp_path/'archive.sqlite')
    result = run_download(req, events.append)
    assert result.error_code == code
    assert 'secret' not in repr(events)
    captured = capsys.readouterr()
    assert 'secret' not in captured.out + captured.err + caplog.text
