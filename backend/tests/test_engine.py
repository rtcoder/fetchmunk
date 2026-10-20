import importlib
from pathlib import Path
import pytest

PNG = bytes.fromhex('89504e470d0a1a0a') + b'fetchmunk-controlled-media'

@pytest.fixture
def engine():
    try:
        return importlib.import_module('fetchmunk_backend.engine')
    except ModuleNotFoundError:
        pytest.fail('gallery-dl adapter is not implemented')

def request(tmp_path, url='https://example.org/photo.png'):
    from fetchmunk_backend.models import WorkerRequest
    return WorkerRequest('job-1', 1, url, tmp_path/'zażółć folder ; test', tmp_path/'archive.sqlite')

def test_download_real_engine(engine, tmp_path, requests_mock):
    requests_mock.get('https://example.org/photo.png', content=PNG)
    events=[]
    result=engine.run_download(request(tmp_path), events.append)
    assert (result.downloaded, result.failed_files, result.error_code)==(1,0,None)
    assert next((tmp_path/'zażółć folder ; test').rglob('*.png')).read_bytes()==PNG
    assert any(e.kind=='file.success' for e in events)

def test_skips_existing_file(engine,tmp_path,requests_mock):
    requests_mock.get('https://example.org/photo.png', content=PNG)
    engine.run_download(request(tmp_path), lambda e:None)
    result=engine.run_download(request(tmp_path), lambda e:None)
    assert (result.downloaded,result.skipped)==(0,1)

def test_ignores_user_config(engine,tmp_path,requests_mock,monkeypatch):
    from gallery_dl import config
    config.set(('extractor',),'download',False)
    config.set(('extractor',),'base-directory',str(tmp_path/'wrong'))
    requests_mock.get('https://example.org/photo.png',content=PNG)
    assert engine.run_download(request(tmp_path),lambda e:None).downloaded==1
    assert not (tmp_path/'wrong').exists()

def test_partial_result(engine,tmp_path,requests_mock):
    def media(id):
        return {'id':id,'ext':'png','is_animated':False,'created_at':'2026-01-01T00:00:00Z','metadata':{'title':''}}
    requests_mock.get('https://api.imgur.com/post/v1/albums/abcde',json={'id':'abcde','title':'Album','created_at':'2026-01-01T00:00:00Z','media':[media('aaaaa'),media('bbbbb')]})
    requests_mock.get('https://i.imgur.com/aaaaa.png',content=PNG)
    requests_mock.get('https://i.imgur.com/bbbbb.png',status_code=404)
    result=engine.run_download(request(tmp_path,'https://imgur.com/a/abcde'),lambda e:None)
    assert result.downloaded==1
    assert result.failed_files==1
    assert result.error_code is not None

def test_unsupported_url(engine,tmp_path):
    result=engine.run_download(request(tmp_path,'https://example.org/not-supported'),lambda e:None)
    assert result.error_code=='unsupported_url'
