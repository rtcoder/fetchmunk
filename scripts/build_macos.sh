#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ "$(uname -m)" != arm64 ]; then echo 'This build targets Apple Silicon.' >&2; exit 1; fi
scripts/build_backend.sh
swift build --package-path macos -c release
SWIFT_BIN="$(swift build --package-path macos -c release --show-bin-path)"
APP="$ROOT/dist/Fetchmunk.app"
# Only remove the generated artifact in this repository.
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$APP/Contents/Helpers"
cp "$SWIFT_BIN/Fetchmunk" "$APP/Contents/MacOS/Fetchmunk"
cp packaging/Info.plist "$APP/Contents/Info.plist"
ditto dist/FetchmunkBackend.app "$APP/Contents/Helpers/FetchmunkBackend.app"
swift packaging/icon.swift build/AppIcon.iconset
iconutil -c icns build/AppIcon.iconset -o "$APP/Contents/Resources/AppIcon.icns"
# Sign actual Mach-O files, then nested frameworks, then the outer bundle.
python3 - "$APP" <<'PY'
from pathlib import Path
import subprocess,sys
app=Path(sys.argv[1])
magic={b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca'}
for p in app.rglob('*'):
    if p.is_file() and not p.is_symlink() and p.parent.name != 'MacOS':
        with p.open('rb') as f:header=f.read(4)
        if header in magic:subprocess.run(['codesign','--force','--sign','-',str(p)],check=True)
for p in sorted(app.rglob('*.framework'),key=lambda p:len(p.parts),reverse=True):
    if not p.is_symlink():subprocess.run(['codesign','--force','--sign','-',str(p)],check=True)
for p in sorted(app.rglob('*.app'),key=lambda p:len(p.parts),reverse=True):
    subprocess.run(['codesign','--force','--sign','-',str(p)],check=True)
subprocess.run(['codesign','--force','--sign','-',str(app)],check=True)
PY
codesign --verify --deep --strict "$APP"
mkdir -p build/dmg
rm -rf build/dmg/Fetchmunk.app
cp -R "$APP" build/dmg/
ln -sfn /Applications build/dmg/Applications
hdiutil create -volname 'Fetchmunk Local Build' -srcfolder build/dmg -ov -format UDZO dist/Fetchmunk-local-arm64.dmg
printf 'Local build: %s\n' "$APP"
