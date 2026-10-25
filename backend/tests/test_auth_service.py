import json, uuid
from test_service import service, call
from fetchmunk_backend.credentials import Vault

class Keys:
    def __init__(self): self.key=None
    def get(self): return self.key
    def set(self,k): self.key=k

def test_auth_never_enters_operation_journal_or_job(service):
    service.vault=Vault(service.store.data_dir/'test-vault',Keys())
    result=service.handle(dict(id='save',method='auth.save',params=dict(id=str(uuid.uuid4()),service='cda',label='My account',kind='password',secret={'username':'private-user','password':'very-secret'})))
    assert 'result' in result,result
    assert 'very-secret' not in json.dumps(result)
    listing=service.handle(dict(id='list',method='auth.list',params={}))
    assert len(listing['result']['profiles'])==1
    assert 'private-user' not in json.dumps(listing)
    created=call(service,'jobs.create',url='https://www.cda.pl/video/abc',destination=str(service.destination))
    assert service.supervisor.request.credentials is None
    assert service.supervisor.request.credential_path == str(service.vault.path)
    assert 'very-secret' not in repr(service.supervisor.request)
    assert 'very-secret' not in json.dumps(service.store.all_jobs())
    assert 'very-secret' not in '\n'.join(service.store.db.iterdump())
    assert 'private-user' not in '\n'.join(service.store.db.iterdump())

def test_cookies_import_requires_explicit_consent(service):
    result=service.handle(dict(id='x',method='auth.import_browser',params={'service':'youtube','browser':'firefox'}))
    assert result['error']['code']=='consent_required'

def test_unrelated_job_never_gets_credentials(service):
    service.vault=Vault(service.store.data_dir/'test-vault',Keys())
    service.vault.save(str(uuid.uuid4()),'cda','My account','password',{'username':'u','password':'secret'})
    call(service,'jobs.create',url='https://cda.pl.evil.test/x',destination=str(service.destination))
    assert service.supervisor.request.credentials is None


def test_auth_dispatcher_keeps_summary_cancel_and_shutdown_responsive(service, monkeypatch):
    import threading
    from fetchmunk_backend.service import AuthDispatcher
    entered, release = threading.Event(), threading.Event()
    responses = []
    def blocked(*args):
        entered.set(); assert release.wait(3)
        return []
    monkeypatch.setattr('fetchmunk_backend.service.BrowserConnector.import_cookies', blocked)
    dispatcher = AuthDispatcher(service, responses.append)
    request = dict(id='auth',method='auth.import_browser',params=dict(id=str(uuid.uuid4()),service='youtube',label='YT',browser='firefox',consent=True))
    created=call(service,'jobs.create',url='https://example.org/a.jpg',destination=str(service.destination))
    dispatcher.submit(request)
    assert entered.wait(1)
    dispatcher.submit({**request,'id':'busy'})
    assert responses[-1]['error']['code']=='auth_busy'
    finished = threading.Event()
    outputs = []
    def commands():
        outputs.append(service.handle(dict(id='summary',method='jobs.summary',params={})))
        outputs.append(call(service,'jobs.cancel',job_id=created['job_id']))
        outputs.append(service.handle(dict(id='shutdown',method='app.shutdown',params={})))
        finished.set()
    consumer=threading.Thread(target=commands,daemon=True);consumer.start()
    try:
        assert finished.wait(0.5), 'auth must not block job commands'
        assert outputs[0]['result']['current_job'] is not None
        assert outputs[-1]['result']['accepted'] is True
    finally:
        dispatcher.close();release.set();consumer.join(2)
    assert dispatcher.thread.daemon


def test_pump_does_not_resolve_credentials(service, monkeypatch):
    service.vault=Vault(service.store.data_dir/'test-vault',Keys())
    service.vault.save(str(uuid.uuid4()),'cda','My account','password',{'username':'u','password':'secret'})
    monkeypatch.setattr(service.vault,'resolve',lambda *_: (_ for _ in ()).throw(AssertionError('Keychain called in coordinator')))
    call(service,'jobs.create',url='https://www.cda.pl/video/abc',destination=str(service.destination))
    assert service.supervisor.request.credential_path==str(service.vault.path)
    assert service.supervisor.request.credentials is None


def test_worker_resolves_credentials_in_child_only(tmp_path, monkeypatch):
    from fetchmunk_backend.models import WorkerRequest, WorkerResult
    from fetchmunk_backend.engine import run_download
    import fetchmunk_backend.credentials as credentials
    calls=[]
    class WorkerVault:
        last_reset = False
        def __init__(self,path): calls.append(str(path))
        def resolve(self,service):
            calls.append(service)
            return {'kind':'password','username':'u','password':'private'}
    monkeypatch.setattr(credentials,'Vault',WorkerVault)
    def video(request, emit):
        assert request.credentials['password']=='private'
        return WorkerResult(downloaded=1)
    monkeypatch.setattr('fetchmunk_backend.video_engine.run_video',video)
    request=WorkerRequest('j',1,'https://www.cda.pl/video/abc',tmp_path/'out',tmp_path/'archive',credential_path=str(tmp_path/'vault'))
    assert run_download(request,lambda _:None).downloaded==1
    assert calls==[str(tmp_path/'vault'),'cda']
    assert request.credentials is None


def test_worker_vault_failure_becomes_needs_auth(service,tmp_path,monkeypatch):
    from fetchmunk_backend.models import WorkerRequest
    from fetchmunk_backend.engine import run_download
    from fetchmunk_backend.credentials import VaultError
    class LockedVault:
        last_reset = False
        def __init__(self,path): pass
        def resolve(self,service): raise VaultError('credential_locked')
    monkeypatch.setattr('fetchmunk_backend.credentials.Vault',LockedVault)
    result=run_download(WorkerRequest('j',1,'https://www.cda.pl/video/abc',tmp_path/'out',tmp_path/'archive',credential_path=str(tmp_path/'vault')),lambda _:None)
    assert result.error_code=='credential_locked'
    created=call(service,'jobs.create',url='https://www.cda.pl/video/abc',destination=str(service.destination))
    service.on_worker(service.supervisor.request,{'kind':'result','data':{'error_code':result.error_code}})
    assert service.store.get_job(created['job_id'])['state']=='needs_auth'


def test_delayed_browser_import_cannot_save_after_shutdown(service,monkeypatch):
    import threading
    entered,release=threading.Event(),threading.Event()
    def blocked(*args):
        entered.set();assert release.wait(3)
        return [{'name':'SID','value':'private','domain':'.youtube.com','path':'/'}]
    monkeypatch.setattr('fetchmunk_backend.service.BrowserConnector.import_cookies',blocked)
    saved=[]
    monkeypatch.setattr(service.vault,'save',lambda *args:saved.append(args))
    response=[]
    thread=threading.Thread(target=lambda:response.append(service.handle(dict(id='auth',method='auth.import_browser',params=dict(id=str(uuid.uuid4()),service='youtube',label='YT',browser='firefox',consent=True)))),daemon=True)
    thread.start();assert entered.wait(1)
    finished=threading.Event()
    closer=threading.Thread(target=lambda:(service.close(),finished.set()),daemon=True);closer.start()
    try: assert finished.wait(.5),'close must not wait for native consent'
    finally: release.set();thread.join(2);closer.join(2)
    assert saved==[]
    assert response[0]['error']['code']=='invalid_state'


def test_missing_worker_key_reports_loss_and_sets_ui_reset(service,tmp_path,monkeypatch):
    from fetchmunk_backend.models import WorkerRequest
    from fetchmunk_backend.engine import run_download
    class LostVault:
        last_reset = False
        def __init__(self,path): pass
        def resolve(self,service): self.last_reset=True;return None
    monkeypatch.setattr('fetchmunk_backend.credentials.Vault',LostVault)
    monkeypatch.setattr('fetchmunk_backend.video_engine.run_video',lambda *_: (_ for _ in ()).throw(AssertionError('must not attempt anonymously after key loss')))
    request=WorkerRequest('j',1,'https://www.cda.pl/video/abc',tmp_path/'out',tmp_path/'archive',credential_path=str(tmp_path/'vault'))
    result=run_download(request,lambda _:None)
    assert result.error_code=='credential_lost'
    created=call(service,'jobs.create',url='https://www.cda.pl/video/abc',destination=str(service.destination))
    service.on_worker(service.supervisor.request,{'kind':'result','data':{'error_code':result.error_code}})
    assert service.store.get_job(created['job_id'])['state']=='needs_auth'
    assert service.handle(dict(id='list',method='auth.list',params={}))['result']['reset'] is True


def test_native_keychain_save_cannot_write_after_service_close(service):
    import threading
    entered,release=threading.Event(),threading.Event()
    class BlockedKeys:
        def get(self):
            entered.set();assert release.wait(3)
            return b'k'*32
        def set(self,key): raise AssertionError('must not create key after close')
    service.vault.key_store=BlockedKeys()
    response=[]
    request=dict(id='save',method='auth.save',params=dict(id=str(uuid.uuid4()),service='cda',label='Account',kind='password',secret={'username':'u','password':'private'}))
    thread=threading.Thread(target=lambda:response.append(service.handle(request)),daemon=True)
    thread.start();assert entered.wait(1)
    service.close()
    release.set();thread.join(2)
    assert not thread.is_alive()
    assert response[0]['error']['code']=='invalid_state'
    assert not service.vault.path.exists()
