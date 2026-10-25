"""Only explicit native credential stores may hold the vault encryption key."""
import base64
import sys
from typing import Protocol


class VaultError(Exception):
    """Safe machine-readable failure; never includes underlying secret-bearing errors."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class KeyStore(Protocol):
    def get(self) -> bytes | None: ...
    def set(self, key: bytes) -> None: ...


class OSKeyStore:
    SERVICE = 'org.fetchmunk.credentials'
    ACCOUNT = 'vault-key-v1'

    def _backend(self):
        # Do not call keyring.get_keyring(): environment/plugin configuration can
        # select plaintext or chained fallbacks. Fail closed instead.
        if sys.platform == 'darwin':
            from keyring.backends.macOS import Keyring
        elif sys.platform == 'win32':
            from keyring.backends.Windows import WinVaultKeyring as Keyring
        elif sys.platform.startswith('linux'):
            from keyring.backends.SecretService import Keyring
        else:
            raise VaultError('credential_unavailable')
        backend = Keyring()
        if backend.priority <= 0:
            raise VaultError('credential_unavailable')
        return backend

    def get(self) -> bytes | None:
        try:
            encoded = self._backend().get_password(self.SERVICE, self.ACCOUNT)
            if encoded is None:
                return None
            key = base64.b64decode(encoded, validate=True)
            if len(key) != 32:
                raise VaultError('credential_unavailable')
            return key
        except Exception as error:
            self._raise_safe(error)

    def set(self, key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) != 32:
            raise VaultError('credential_unavailable')
        try:
            self._backend().set_password(
                self.SERVICE, self.ACCOUNT, base64.b64encode(key).decode('ascii'))
        except Exception as error:
            self._raise_safe(error)

    @staticmethod
    def _raise_safe(error):
        from keyring.errors import KeyringLocked
        code = 'credential_locked' if isinstance(error, KeyringLocked) else 'credential_unavailable'
        raise VaultError(code) from None
