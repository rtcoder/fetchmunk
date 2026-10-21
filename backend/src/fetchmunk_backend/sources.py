"""Local URL-pattern recognition for the pinned gallery-dl engine."""

from .url_validation import validate_url


def inspect_source(url: str) -> dict:
    validate_url(url)
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
