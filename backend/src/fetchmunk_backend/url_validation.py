"""Shared syntactic URL validation; never performs network or extractor work."""

import unicodedata
from urllib.parse import SplitResult, urlsplit
from .store import StoreError


def validate_url(value) -> SplitResult:
    if (not isinstance(value, str) or not value or len(value) > 16384
            or any(c.isspace() or unicodedata.category(c) == 'Cc' for c in value)):
        raise StoreError('invalid_url')
    try:
        value.encode('utf-8')
        parsed = urlsplit(value)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            raise ValueError()
        # Accessing .port validates both the numeric spelling and its range.
        parsed.port
    except (ValueError, UnicodeError):
        raise StoreError('invalid_url') from None
    return parsed
