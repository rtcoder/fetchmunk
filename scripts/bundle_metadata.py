"""Build notices from installed metadata for files collected by PyInstaller.

No dependency traversal: installed development packages are not shipped packages.
The inventory is generated directly from the packaging Analysis in backend.spec.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import plistlib
import re
import sysconfig

LIMITATIONS = (
    'Generated from installed distribution metadata and the PyInstaller collection inventory. '
    'Only available license/notice texts are copied; missing texts are listed explicitly. '
    'Python LICENSE.txt is included. Native libraries embedded in the Python distribution, '
    'vendored code and system frameworks need a separate provenance and license review. '
    'This inventory is not a complete legal audit and does not choose a Fetchmunk license.'
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(resources, app_version, python_version, python_license, sources, distributions):
    if not python_license.is_file() or not python_license.read_bytes().strip():
        raise ValueError('Bundled Python license text is missing')
    resources.mkdir(parents=True, exist_ok=True)
    licenses = resources / 'licenses'
    licenses.mkdir(exist_ok=True)
    collected = {Path(p).resolve() for p in sources}
    records = []
    hashes = {}
    for dist in sorted(distributions, key=lambda d: d.metadata['Name'].lower()):
        files = list(dist.files or [])
        if not any(Path(dist.locate_file(f)).resolve() in collected for f in files):
            continue
        name = dist.metadata['Name']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
            raise ValueError('Invalid distribution name')
        dest = licenses / name
        copied = []
        has_license_text = False
        for file in sorted(files, key=str):
            # Copy metadata notices, not arbitrary files or private build config.
            parts = file.parts
            if not any(p.endswith('.dist-info') for p in parts):
                continue
            if not (any(p.lower() == 'licenses' for p in parts) or
                    file.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'AUTHORS'))):
                continue
            source = Path(dist.locate_file(file))
            if not source.is_file() or not source.read_bytes().strip():
                continue
            dest.mkdir(exist_ok=True)
            # Stable index prevents collisions between multiple metadata subdirectories.
            target = dest / f'{len(copied):02d}-{file.name}'
            target.write_bytes(source.read_bytes())
            relative = target.relative_to(resources).as_posix()
            copied.append(relative)
            if file.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING')):
                has_license_text = True
            hashes[relative] = digest(target)
        records.append({'name': name, 'version': dist.version, 'license_files': copied, 'has_license_text': has_license_text})
    engine = next((d['version'] for d in records if d['name'].lower().replace('_', '-') == 'gallery-dl'), None)
    if engine is None:
        raise ValueError('gallery-dl is absent from the collected distribution inventory')
    target = licenses / 'Python-LICENSE.txt'
    target.write_bytes(python_license.read_bytes())
    python_relative = target.relative_to(resources).as_posix()
    hashes[python_relative] = digest(target)
    missing = [d['name'] for d in records if not d['has_license_text']]
    lines = ['Fetchmunk — third-party notices', '', LIMITATIONS, '',
             f'Python {python_version}: {python_relative}', '']
    for record in records:
        lines.append(f"{record['name']} {record['version']}")
        lines.extend(record['license_files'])
        if not record['has_license_text']:
            lines.append(f"MISSING LICENSE TEXT: {record['name']}")
        lines.append('')
    notices = resources / 'THIRD_PARTY_NOTICES.txt'
    notices.write_text('\n'.join(lines), encoding='utf-8')
    hashes[notices.name] = digest(notices)
    manifest = {
        'schema_version': 1, 'app_version': app_version,
        'gallery_dl_version': engine, 'python_version': python_version,
        'python_license': python_relative, 'distributions': records,
        'missing_license_texts': missing, 'limitations': LIMITATIONS,
        'sha256': hashes,
    }
    (resources / 'build-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return manifest


def validate(resources, app_version):
    """Validate shipped records and hashes without requiring build-time packages."""
    try:
        manifest = json.loads((resources / 'build-manifest.json').read_text())
        if manifest['schema_version'] != 1 or manifest['app_version'] != app_version:
            raise ValueError('Bundle manifest version mismatch')
        for key in ('python_version', 'gallery_dl_version', 'limitations'):
            if not isinstance(manifest[key], str) or not manifest[key].strip():
                raise ValueError('Incomplete bundle manifest')
        records = manifest['distributions']
        engine = next(d for d in records if d['name'].lower().replace('_', '-') == 'gallery-dl')
        if engine['version'] != manifest['gallery_dl_version']:
            raise ValueError('Engine manifest version mismatch')
        if manifest['missing_license_texts'] != [d['name'] for d in records if not d['has_license_text']]:
            raise ValueError('Missing license report mismatch')
        required = {'THIRD_PARTY_NOTICES.txt', manifest['python_license']}
        required.update(f for d in records for f in d['license_files'])
        if required != set(manifest['sha256']):
            raise ValueError('License hash inventory mismatch')
        for relative, expected in manifest['sha256'].items():
            path = resources / relative
            if Path(relative).is_absolute() or '..' in Path(relative).parts or not path.resolve().is_relative_to(resources.resolve()):
                raise ValueError('Invalid manifest resource path')
            if not path.is_file() or not path.read_bytes().strip() or digest(path) != expected:
                raise ValueError('Missing or changed notice/license resource')
        return manifest
    except (OSError, KeyError, TypeError, StopIteration, json.JSONDecodeError) as error:
        raise ValueError('Missing or invalid bundle manifest/notices') from error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resources', required=True, type=Path)
    parser.add_argument('--info-plist', required=True, type=Path)
    parser.add_argument('--inventory', required=True, type=Path)
    args = parser.parse_args()
    with args.info_plist.open('rb') as stream:
        version = plistlib.load(stream)['CFBundleShortVersionString']
    inventory = json.loads(args.inventory.read_text())
    result = generate(args.resources, version, platform.python_version(),
                      Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt',
                      inventory, importlib.metadata.distributions())
    validate(args.resources, version)
    print(json.dumps({'distributions': len(result['distributions']),
                      'missing_license_texts': result['missing_license_texts'],
                      'limitations': LIMITATIONS}))


if __name__ == '__main__':
    main()
