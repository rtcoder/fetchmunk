"""Reject bundled Mach-O code requiring a newer OS than the app promises."""
import pathlib
import re
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
maximum = (13, 0)
magic = {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
failures = []
count = 0
for path in root.rglob('*'):
    if not path.is_file() or path.is_symlink():
        continue
    with path.open('rb') as handle:
        if handle.read(4) not in magic:
            continue
    count += 1
    output = subprocess.check_output(['xcrun', 'vtool', '-show-build', str(path)], text=True)
    versions = re.findall(r'minos\s+(\d+)\.(\d+)', output)
    if not versions and 'LC_VERSION_MIN_MACOSX' in output:
        versions = re.findall(r'version\s+(\d+)\.(\d+)', output)
    if not versions or any(tuple(map(int, version)) > maximum for version in versions):
        failures.append(str(path.relative_to(root)) + ': ' + repr(versions))
if not count:
    failures.append('No Mach-O files found')
if failures:
    sys.exit('\n'.join(failures))
print(f'{count} Mach-O files: deployment target <= macOS 13.0')
