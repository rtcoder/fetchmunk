#!/usr/bin/env python3
"""Export installed engines' class metadata without instances or user configuration."""
from __future__ import annotations

import argparse
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import re
import random
from urllib.parse import urlsplit


def static(cls, name, default=None):
    return inspect.getattr_static(cls, name, default)


def strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, re.Pattern):
        return [value.pattern]
    if isinstance(value, (list, tuple)):
        return [item for entry in value for item in strings(entry)]
    return []


def record(cls, engine):
    patterns = strings(static(cls, 'pattern' if engine == 'gallery-dl' else '_VALID_URL'))
    examples = []
    for name in ('example', '_TEST', '_TESTS'):
        value = static(cls, name)
        if name == 'example':
            examples.extend(strings(value))
        else:
            for test in value if isinstance(value, (list, tuple)) else [value]:
                if isinstance(test, dict) and isinstance(test.get('url'), str):
                    examples.append(test['url'])
    roots = []
    for name in ('root', 'base_url', '_BASE_URL', '_ROOT_URL'):
        roots.extend(strings(static(cls, name)))
    domains = set()
    for url in examples + roots:
        try:
            parsed = urlsplit(url)
            if parsed.scheme in ('http', 'https') and parsed.hostname:
                domains.add(parsed.hostname.lower())
        except ValueError:
            pass
    identifier = static(cls, 'IE_NAME') if engine == 'yt-dlp' else cls.__name__
    return {
        'id': identifier if isinstance(identifier, str) else cls.__name__,
        'class': cls.__name__, 'module': cls.__module__,
        'category': static(cls, 'category') if engine == 'gallery-dl' else None,
        'subcategory': static(cls, 'subcategory') if engine == 'gallery-dl' else None,
        'patterns': sorted(set(patterns)),
        'example_urls': sorted(set(examples)),
        'declared_roots': sorted(set(roots)),
        'observed_domains': sorted(domains),
    }


def collect():
    # Some upstream class fixtures choose an example host at import time.
    state = random.getstate()
    try:
        random.seed(0)
        return _collect()
    finally:
        random.setstate(state)


def _collect():
    # Full classes retain test URLs omitted by the lazy class registry.
    # No YoutubeDL object, extractor instance, config loader or network request.
    os.environ['YTDLP_NO_LAZY_EXTRACTORS'] = '1'
    from gallery_dl import extractor as gallery
    from yt_dlp import extractor as video
    engines = (('gallery-dl', gallery.extractors()), ('yt-dlp', video.gen_extractor_classes()))
    result = {}
    for engine, classes in engines:
        records = sorted((record(cls, engine) for cls in classes), key=lambda row: (row['id'], row['class']))
        result[engine] = {
            'schema_version': 1, 'engine': engine,
            'version': importlib.metadata.version(engine),
            'extractor_count': len(records),
            'domain_scope': 'Observed hosts from declared roots and example/test URLs only; not exhaustive. URL regexes and generic extractors may support additional domains. Tests may contain obsolete URLs. Presence does not guarantee a working download.',
            'extractors': records,
        }
    return result


def render_text(data):
    lines = [f"{data['engine']} {data['version']} — {data['extractor_count']} extractors", data['domain_scope'], '']
    for row in data['extractors']:
        lines.extend([f"{row['id']} [{row['class']}]", f"  Module: {row['module']}"])
        for label, key in [('Pattern', 'patterns'), ('Root', 'declared_roots'), ('Example', 'example_urls'), ('Observed domain', 'observed_domains')]:
            lines.extend(f'  {label}: {value}' for value in row[key])
        lines.append('')
    return '\n'.join(lines) + '\n'


def export(output):
    output.mkdir(parents=True, exist_ok=True)
    for engine, data in collect().items():
        (output / f'{engine}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (output / f'{engine}.txt').write_text(render_text(data), encoding='utf-8')
        print(f"{engine} {data['version']}: {data['extractor_count']} extractors")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'docs' / 'sources')
    export(parser.parse_args().output)
