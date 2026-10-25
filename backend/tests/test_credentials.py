import importlib
import json
import os
import uuid
import pytest


def api():
    try:
        return importlib.import_module('fetchmunk_backend.credentials')
    except ModuleNotFoundError:
        pytest.fail('encrypted credential vault missing')


class MemoryKeyStore:
    key = None
    error = None
    def get(self):
        if self.error:
            raise api().VaultError(self.error)
        return self.key
    def set(self, key):
        if self.error:
            raise api().VaultError(self.error)
        self.key = key


def make(tmp_path):
    store = MemoryKeyStore()
    return api().Vault(tmp_path / 'private' / 'vault.json', store), store


def save(vault, service='cda', kind='password', secret=None, profile_id=None):
    return vault.save(profile_id or str(uuid.uuid4()), service, 'Personal', kind,
                      secret or {'username': 'alice-private', 'password': 'secret-private'})


def test_encrypt_roundtrip_metadata_permissions_and_new_nonce(tmp_path):
    vault, store = make(tmp_path)
    profile = save(vault)
    path = tmp_path / 'private' / 'vault.json'
    first = path.read_bytes()
    assert b'alice-private' not in first and b'secret-private' not in first
    assert len(store.key) == 32
    assert vault.list_profiles() == [profile]
    assert set(profile) == {'id', 'service', 'label', 'kind'}
    assert api().Vault(path, store).resolve('cda') == {
        'kind': 'password', 'username': 'alice-private', 'password': 'secret-private'}
    save(vault, profile_id=profile['id'])
    assert path.read_bytes() != first
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700


def test_replace_service_and_delete_are_idempotent(tmp_path):
    vault, _ = make(tmp_path)
    save(vault)
    replacement = save(vault)
    assert vault.list_profiles() == [replacement]
    vault.delete(replacement['id'])
    vault.delete(replacement['id'])
    assert vault.resolve('cda') is None


def test_key_loss_clears_records_and_allows_fresh_save(tmp_path):
    vault, store = make(tmp_path)
    save(vault)
    store.key = None
    assert vault.resolve('cda') is None
    assert vault.last_reset and vault.list_profiles() == []
    save(vault)
    assert vault.resolve('cda')['password'] == 'secret-private'


@pytest.mark.parametrize('error', ['credential_locked', 'credential_unavailable'])
def test_transient_store_failures_preserve_file(tmp_path, error):
    vault, store = make(tmp_path)
    save(vault)
    path = tmp_path / 'private' / 'vault.json'
    before = path.read_bytes()
    store.error = error
    with pytest.raises(api().VaultError, match=error):
        vault.resolve('cda')
    with pytest.raises(api().VaultError, match=error):
        save(vault)
    assert path.read_bytes() == before


@pytest.mark.parametrize('field,value', [('id', '18d1f933-ea19-4055-9e32-55c96e54f348'),
                                        ('service', 'youtube'), ('kind', 'cookies')])
def test_metadata_is_authenticated(tmp_path, field, value):
    vault, _ = make(tmp_path)
    save(vault)
    path = tmp_path / 'private' / 'vault.json'
    data = json.loads(path.read_text())
    data['profiles'][0][field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(api().VaultError, match='credential_lost'):
        vault.resolve(value if field == 'service' else 'cda')
    assert vault.list_profiles() == []


def test_ciphertext_swap_is_rejected(tmp_path):
    vault, _ = make(tmp_path)
    save(vault)
    save(vault, service='youtube', kind='cookies', secret={'cookies': [
        {'name': 'SID', 'value': 'secret-cookie', 'domain': '.youtube.com', 'path': '/', 'secure': True}]})
    path = tmp_path / 'private' / 'vault.json'
    data = json.loads(path.read_text())
    a, b = data['profiles']
    a['ciphertext'], b['ciphertext'] = b['ciphertext'], a['ciphertext']
    a['nonce'], b['nonce'] = b['nonce'], a['nonce']
    path.write_text(json.dumps(data))
    with pytest.raises(api().VaultError, match='credential_lost'):
        vault.resolve('cda')
    assert len(vault.list_profiles()) == 1


@pytest.mark.parametrize('service,kind,secret', [
    ('youtube', 'password', {'username': 'u', 'password': 'p'}),
    ('unknown', 'password', {'username': 'u', 'password': 'p'}),
    ('cda', 'password', {'username': [], 'password': 'p'}),
    ('cda', 'cookies', {'cookies': []}),
    ('cda', 'cookies', {'cookies': [{'name': 'x', 'value': {}}]}),
])
def test_invalid_credentials_rejected_without_writing(tmp_path, service, kind, secret):
    vault, _ = make(tmp_path)
    with pytest.raises(api().VaultError, match='invalid_credentials'):
        save(vault, service, kind, secret)
    assert vault.list_profiles() == []


def test_os_store_ignores_generic_keyring_backend(monkeypatch):
    keyring = pytest.importorskip('keyring')
    monkeypatch.setattr(keyring, 'get_keyring', lambda: pytest.fail('generic fallback used'))
    mod = importlib.import_module('fetchmunk_backend.key_store')
    monkeypatch.setattr(mod.sys, 'platform', 'unsupported')
    with pytest.raises(api().VaultError, match='credential_unavailable'):
        mod.OSKeyStore().get()


@pytest.mark.parametrize('failure,code', [('locked', 'credential_locked'), ('denied', 'credential_unavailable')])
def test_os_store_errors_never_mean_missing(monkeypatch, failure, code):
    mod = importlib.import_module('fetchmunk_backend.key_store')
    from keyring.errors import KeyringLocked
    class Backend:
        def get_password(self, *args):
            if failure == 'locked':
                raise KeyringLocked('sensitive native detail')
            raise RuntimeError('sensitive native detail')
    monkeypatch.setattr(mod.OSKeyStore, '_backend', lambda self: Backend())
    with pytest.raises(api().VaultError) as error:
        mod.OSKeyStore().get()
    assert str(error.value) == code
    assert error.value.__suppress_context__


def test_os_store_only_explicit_absence_returns_none(monkeypatch):
    mod = importlib.import_module('fetchmunk_backend.key_store')
    class Backend:
        value = None
        def get_password(self, *args):
            return self.value
    backend = Backend()
    monkeypatch.setattr(mod.OSKeyStore, '_backend', lambda self: backend)
    assert mod.OSKeyStore().get() is None
    for invalid in ('', 'bad-base64!', 'c2hvcnQ='):
        backend.value = invalid
        with pytest.raises(api().VaultError, match='credential_unavailable'):
            mod.OSKeyStore().get()


def test_cookie_roundtrip_and_secret_not_in_metadata(tmp_path):
    vault, _ = make(tmp_path)
    cookies = [{'name': 'SID', 'value': 'cookie-secret', 'domain': '.youtube.com',
                'path': '/', 'secure': True, 'expires': 2000000000}]
    save(vault, 'youtube', 'cookies', {'cookies': cookies})
    assert vault.resolve('youtube') == {'kind': 'cookies', 'cookies': cookies}
    assert 'cookie-secret' not in json.dumps(vault.list_profiles())
    assert 'cookie-secret' not in (tmp_path / 'private' / 'vault.json').read_text()


def test_unrelated_service_does_not_access_key_store(tmp_path):
    class Store:
        key = None
        locked = False
        def get(self):
            if self.locked: raise api().VaultError('credential_locked')
            return self.key
        def set(self, key): self.key = key
    store = Store()
    vault = api().Vault(tmp_path/'vault.json', store)
    vault.save(str(uuid.uuid4()), 'cda', 'Account', 'password', {'username':'u', 'password':'p'})
    store.locked = True
    assert vault.resolve('youtube') is None


def test_delayed_key_access_cannot_write_after_close(tmp_path):
    import threading
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
    class BlockingStore(MemoryKeyStore):
        def get(self):
            entered.set()
            assert release.wait(3)
            return b'k' * 32
    path = tmp_path / 'vault.json'
    vault = api().Vault(path, BlockingStore(), write_allowed=lambda: not stopped.is_set())
    errors = []
    def operation():
        try: save(vault)
        except api().VaultError as error: errors.append(error.code)
    thread = threading.Thread(target=operation, daemon=True)
    thread.start()
    assert entered.wait(1)
    stopped.set(); release.set(); thread.join(2)
    assert not thread.is_alive()
    assert errors == ['invalid_state']
    assert not path.exists()


def test_metadata_listing_does_not_wait_for_keychain(tmp_path):
    import threading
    vault, store = make(tmp_path)
    save(vault)
    entered, release = threading.Event(), threading.Event()
    key = store.key
    def blocked():
        entered.set()
        assert release.wait(3)
        return key
    store.get = blocked
    worker = threading.Thread(target=lambda: vault.resolve('cda'), daemon=True)
    worker.start(); assert entered.wait(1)
    done = threading.Event()
    reader = threading.Thread(target=lambda: (vault.list_profiles(), done.set()), daemon=True)
    reader.start()
    try: assert done.wait(0.5), 'metadata must not wait on keychain consent'
    finally: release.set();worker.join(2);reader.join(2)


def test_concurrent_process_save_preserves_other_service(tmp_path):
    import subprocess, sys, threading
    path = tmp_path / 'vault.json'
    entered, release = threading.Event(), threading.Event()
    class BlockingStore(MemoryKeyStore):
        def get(self):
            entered.set()
            assert release.wait(5)
            return b'k' * 32
    vault = api().Vault(path, BlockingStore())
    errors = []
    def first_save():
        try: save(vault)
        except Exception as error: errors.append(type(error).__name__)
    first = threading.Thread(target=first_save, daemon=True)
    first.start();assert entered.wait(1)
    script = """
import sys, uuid
from pathlib import Path
from fetchmunk_backend.credentials import Vault
class Store:
    def get(self): return b'k' * 32
    def set(self, key): pass
print('started',flush=True)
Vault(Path(sys.argv[1]), Store()).save(str(uuid.uuid4()), 'youtube', 'YT', 'cookies', {'cookies':[{'name':'SID','value':'value','domain':'.youtube.com','path':'/'}]})
print('saved',flush=True)
"""
    env = {**os.environ, 'PYTHONPATH': str(__import__('pathlib').Path(api().__file__).parents[1])}
    second = subprocess.Popen([sys.executable, '-c', script, str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        assert second.stdout.readline().strip() == 'started'
        with pytest.raises(subprocess.TimeoutExpired): second.wait(timeout=0.15)
        release.set();first.join(2)
        stdout, stderr = second.communicate(timeout=3)
        assert second.returncode == 0, stderr
        assert stdout.strip() == 'saved'
        assert errors == []
        assert {p['service'] for p in vault.list_profiles()} == {'cda','youtube'}
        if os.name != 'nt':
            assert path.with_suffix('.json.lock').stat().st_mode & 0o777 == 0o600
    finally:
        release.set();first.join(2)
        if second.poll() is None: second.kill()
        second.communicate()
