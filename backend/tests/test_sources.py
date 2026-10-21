import importlib
import socket

import pytest


@pytest.mark.parametrize('url,category,subcategory', [
    ('https://imgur.com/a/abcde', 'imgur', 'album'),
    ('https://www.pixiv.net/artworks/12345678', 'pixiv', 'work'),
    ('https://example.org/photo.png', 'directlink', None),
    ('https://example.org/not-supported', None, None),
])
def test_inspection_matches_pinned_patterns_without_side_effects(monkeypatch, url, category, subcategory):
    from gallery_dl import config
    from gallery_dl.extractor.common import Extractor
    import requests

    def forbidden(*args, **kwargs):
        pytest.fail('source inspection attempted I/O or extractor construction')

    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(requests.Session, 'request', forbidden)
    monkeypatch.setattr(Extractor, '__init__', forbidden)
    monkeypatch.setattr(config, 'load', forbidden)
    monkeypatch.setattr(Extractor, 'cookies_load', forbidden)
    sources = importlib.import_module('fetchmunk_backend.sources')
    assert sources.inspect_source(url) == {
        'supported': category is not None, 'category': category, 'subcategory': subcategory,
    }


@pytest.mark.parametrize('url', ['file:///tmp/file', 'https://user:secret@imgur.com/a/abcde', 'https://imgur.com:bad/a/abcde'])
def test_inspection_rejects_invalid_urls(url):
    from fetchmunk_backend.store import StoreError
    sources = importlib.import_module('fetchmunk_backend.sources')
    with pytest.raises(StoreError, match='invalid_url'):
        sources.inspect_source(url)
