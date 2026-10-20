import importlib
import pytest


def test_secrets_and_urls_are_redacted():
    try:
        d = importlib.import_module("fetchmunk_backend.diagnostics")
    except ModuleNotFoundError:
        pytest.fail("diagnostics redaction missing")
    text = d.redact_diagnostic(
        "Cookie: secret-session\nAuthorization: Bearer secret-token\nhttps://host/path?token=secret-query"
    )
    assert "secret-" not in text
    assert "https://" not in text
