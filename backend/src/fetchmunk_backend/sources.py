"""Local URL-pattern recognition for the pinned gallery-dl engine."""

from .url_validation import validate_url


def inspect_source(url: str) -> dict:
    url = normalize_source_url(url)
    from .browser_credentials import service_for_url
    service = service_for_url(url)
    if service:
        return {'supported': True, 'category': service, 'subcategory': 'video', 'engine': 'yt-dlp'}
    from gallery_dl import extractor

    # Pinned private API: preserve find() precedence but never instantiate an
    # extractor (constructors may load cookies or consult user configuration).
    for cls in extractor._list_classes():
        if cls.pattern.match(url):
            return {
                'supported': True,
                'category': cls.category,
                'subcategory': cls.subcategory or None,
            }
    return {'supported': False, 'category': None, 'subcategory': None}

# Explicit localized host supplied by the user. No wildcard, guessed languages
# or changes to the extractor; live availability remains an engine concern.
SOURCE_ALIASES: dict[str, str] = {"pl.fapello.com": "fapello.com"}

def normalize_source_url(url: str, aliases=None) -> str:
    from urllib.parse import urlunsplit
    parsed = validate_url(url)
    target = (SOURCE_ALIASES if aliases is None else aliases).get(parsed.hostname.lower())
    if target is None:
        return url
    netloc = target + (':' + str(parsed.port) if parsed.port is not None else '')
    normalized = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    validate_url(normalized)
    return normalized
