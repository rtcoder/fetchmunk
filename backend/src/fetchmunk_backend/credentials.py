"""Encrypted local credentials. Public metadata never contains secret fields."""
from contextlib import contextmanager
import base64
import errno
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .key_store import KeyStore, OSKeyStore, VaultError

_MAX_BYTES = 4 * 1024 * 1024


def _metadata(record):
    return {key: record[key] for key in ('id', 'service', 'label', 'kind')}


def _aad(record):
    return json.dumps([1, record['id'], record['service'], record['kind']],
                      separators=(',', ':')).encode()


def _text(value, maximum, *, empty=False):
    return isinstance(value, str) and (empty or bool(value)) and len(value) <= maximum and '\x00' not in value


def _validate(profile_id, service, label, kind, secret):
    try:
        valid_id = isinstance(profile_id, str) and str(uuid.UUID(profile_id)) == profile_id
    except (ValueError, AttributeError):
        valid_id = False
    if not valid_id or service not in ('youtube', 'cda') or not _text(label, 120):
        raise VaultError('invalid_credentials')
    if not isinstance(secret, dict):
        raise VaultError('invalid_credentials')
    if kind == 'password':
        valid = service == 'cda' and set(secret) == {'username', 'password'} and all(
            _text(secret[k], 4096) for k in ('username', 'password'))
    elif kind == 'cookies':
        cookies = secret.get('cookies')
        valid = set(secret) == {'cookies'} and isinstance(cookies, list) and 0 < len(cookies) <= 3000
        if valid:
            for cookie in cookies:
                if not isinstance(cookie, dict) or not all(
                    _text(cookie.get(k), 16384 if k == 'value' else 1024, empty=k == 'value')
                    for k in ('name', 'value', 'domain', 'path')
                ) or not isinstance(cookie.get('secure', False), bool):
                    valid = False
                    break
                if any(not isinstance(v, (str, bool, int, float, type(None))) for v in cookie.values()):
                    valid = False
                    break
    else:
        valid = False
    if not valid:
        raise VaultError('invalid_credentials')
    try:
        encoded = json.dumps(secret, allow_nan=False).encode()
    except (ValueError, TypeError):
        raise VaultError('invalid_credentials') from None
    if len(encoded) > _MAX_BYTES // 2:
        raise VaultError('invalid_credentials')
    return encoded


class Vault:
    def __init__(self, path: Path, key_store: KeyStore | None = None, *, write_allowed=None):
        self.path = Path(path)
        self.key_store = key_store if key_store is not None else OSKeyStore()
        self.last_reset = False
        self._lock = threading.RLock()
        self._write_allowed = write_allowed or (lambda: True)

    def _ensure_open(self):
        if not self._write_allowed():
            raise VaultError('invalid_state')

    @contextmanager
    def _transaction(self):
        # Every mutating transaction takes locks in the same order: thread, file.
        # The lock inode is stable; only the encrypted data file is replaced.
        with self._lock:
            self._ensure_open()
            descriptor = None
            acquired = False
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chmod(self.path.parent, 0o700)
                lock_path = self.path.with_suffix(self.path.suffix + '.lock')
                descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
                os.chmod(lock_path, 0o600)
                if os.name == 'nt':
                    import msvcrt
                    if os.fstat(descriptor).st_size == 0:
                        os.write(descriptor, b'\0')
                else:
                    import fcntl
                while not acquired:
                    self._ensure_open()
                    try:
                        if os.name == 'nt':
                            os.lseek(descriptor, 0, os.SEEK_SET)
                            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                        else:
                            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                    except OSError as error:
                        if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                            raise
                        time.sleep(0.025)
                self._ensure_open()
                yield
            except OSError:
                raise VaultError('credential_unavailable') from None
            finally:
                if descriptor is not None:
                    if acquired:
                        if os.name == 'nt':
                            os.lseek(descriptor, 0, os.SEEK_SET)
                            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                        else:
                            fcntl.flock(descriptor, fcntl.LOCK_UN)
                    os.close(descriptor)

    def _read(self):
        try:
            if not self.path.exists():
                return []
            if self.path.stat().st_size > _MAX_BYTES:
                raise VaultError('credential_unavailable')
            document = json.loads(self.path.read_bytes())
            if document.get('version') != 1 or not isinstance(document.get('profiles'), list):
                raise VaultError('credential_unavailable')
            records = document['profiles']
            if len(records) > 2 or any(not isinstance(r, dict) or not all(
                isinstance(r.get(k), str) for k in ('id', 'service', 'label', 'kind', 'nonce', 'ciphertext')
            ) for r in records):
                raise VaultError('credential_unavailable')
            return records
        except (OSError, ValueError, TypeError, AttributeError):
            raise VaultError('credential_unavailable') from None

    def _write(self, records):
        self._ensure_open()
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.path.parent, 0o700)
            descriptor, temporary = tempfile.mkstemp(prefix='.credentials-', dir=self.path.parent)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                os.chmod(temporary, 0o600)
                json.dump({'version': 1, 'profiles': records}, stream, separators=(',', ':'))
                stream.flush()
                os.fsync(stream.fileno())
            self._ensure_open()
            os.replace(temporary, self.path)
            temporary = None
        except OSError:
            raise VaultError('credential_unavailable') from None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def _key(self, records, *, create=False):
        key = self.key_store.get()
        self._ensure_open()
        if key is None:
            if records:
                self._write([])
                records.clear()
                self.last_reset = True
            if create:
                key = os.urandom(32)
                self.key_store.set(key)
                self._ensure_open()
        elif not isinstance(key, bytes) or len(key) != 32:
            raise VaultError('credential_unavailable')
        return key

    def list_profiles(self) -> list[dict]:
        # Atomic replace makes each metadata read a consistent snapshot. Do not
        # wait for a transaction whose OS key-store consent prompt is open.
        return [_metadata(record) for record in self._read()]

    def save(self, profile_id, service, label, kind, secret: dict) -> dict:
        encoded = _validate(profile_id, service, label, kind, secret)
        with self._transaction():
            records = self._read()
            key = self._key(records, create=True)
            record = {'id': profile_id, 'service': service, 'label': label, 'kind': kind}
            nonce = os.urandom(12)
            ciphertext = AESGCM(key).encrypt(nonce, encoded, _aad(record))
            record.update(nonce=base64.b64encode(nonce).decode('ascii'),
                          ciphertext=base64.b64encode(ciphertext).decode('ascii'))
            records = [r for r in records if r['id'] != profile_id and r['service'] != service]
            self._write([*records, record])
            return _metadata(record)

    def delete(self, profile_id) -> None:
        with self._transaction():
            records = self._read()
            remaining = [r for r in records if r['id'] != profile_id]
            if remaining != records:
                self._write(remaining)

    def resolve(self, service) -> dict | None:
        with self._transaction():
            records = self._read()
            record = next((r for r in records if r['service'] == service), None)
            if record is None:
                return None
            key = self._key(records)
            if key is None:
                return None
            try:
                nonce = base64.b64decode(record['nonce'], validate=True)
                ciphertext = base64.b64decode(record['ciphertext'], validate=True)
                if len(nonce) != 12:
                    raise ValueError()
                secret = json.loads(AESGCM(key).decrypt(nonce, ciphertext, _aad(record)))
                _validate(record['id'], service, record['label'], record['kind'], secret)
            except (InvalidTag, ValueError, TypeError, VaultError):
                self._write([r for r in records if r is not record])
                self.last_reset = True
                raise VaultError('credential_lost') from None
            return {'kind': record['kind'], **secret}
