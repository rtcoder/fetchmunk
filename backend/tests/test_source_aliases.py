from fetchmunk_backend.sources import normalize_source_url

def test_no_heuristic_stripping_or_host_substring_matching():
    for url in ['https://pl.example.com/a?x=1','https://youtube.com.evil.test/a']:
        assert normalize_source_url(url)==url

def test_explicit_alias_preserves_path_query_fragment():
    url='https://pl.example.com/a%2Fb?token=abc#part'
    assert normalize_source_url(url,{'pl.example.com':'example.com'})=='https://example.com/a%2Fb?token=abc#part'
    assert normalize_source_url('https://pl.example.com.evil.test/a',{'pl.example.com':'example.com'})=='https://pl.example.com.evil.test/a'

def test_polish_fapello_alias_matches_model_and_post_without_network(monkeypatch):
    import socket
    from fetchmunk_backend.sources import inspect_source
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: (_ for _ in ()).throw(AssertionError('network forbidden')))
    for path, category in [('/example-model/', 'model'), ('/example-model/123/', 'post')]:
        original = 'https://pl.fapello.com' + path
        assert normalize_source_url(original) == 'https://fapello.com' + path
        assert inspect_source(original) == {'supported': True, 'category': 'fapello', 'subcategory': category}
    assert normalize_source_url('https://pl.fapello.com/example-model/123/?x=1#part') == 'https://fapello.com/example-model/123/?x=1#part'

def test_fapello_alias_does_not_rewrite_other_hosts():
    for host in ['pl.fapello.com.evil.test', 'unverified.fapello.com', 'pl.fapello.su']:
        url = 'https://' + host + '/example-model/'
        assert normalize_source_url(url) == url

def test_worker_normalizes_without_changing_original_request(tmp_path, monkeypatch):
    from gallery_dl import job
    from fetchmunk_backend.engine import run_download
    from fetchmunk_backend.models import WorkerRequest
    seen = []
    class FakeDownloadJob:
        def __init__(self, url): seen.append(url)
        def run(self): return 0
    monkeypatch.setattr(job, 'DownloadJob', FakeDownloadJob)
    original = 'https://pl.fapello.com/example-model/'
    request = WorkerRequest('test', 1, original, tmp_path/'files', tmp_path/'archive.sqlite')
    assert run_download(request, lambda event: None).error_code is None
    assert seen == ['https://fapello.com/example-model/']
    assert request.url == original
