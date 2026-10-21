from PyInstaller.utils.hooks import collect_submodules, collect_data_files
from pathlib import Path
import json
root = Path(SPECPATH).parent
hidden = collect_submodules('gallery_dl')
a = Analysis([str(root/'backend/src/fetchmunk_backend/__main__.py')],
             pathex=[str(root/'backend/src')],
             datas=collect_data_files('gallery_dl') + collect_data_files('certifi'),
             hiddenimports=hidden, excludes=['pytest','requests_mock','yt_dlp','tkinter'])
# Inventory contains build-local paths only and is never copied into the app.
# Match collected source files to installed dist-info records, including runtime hooks.
(root / 'build' / 'runtime-sources.json').write_text(json.dumps(
    sorted({str(source) for _, source, _ in [*a.pure, *a.binaries, *a.datas, *a.scripts]})))
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='fetchmunk-backend',
          console=True, target_arch='arm64')
coll = COLLECT(exe, a.binaries, a.datas, name='fetchmunk-backend')

app = BUNDLE(coll, name='FetchmunkBackend.app', bundle_identifier='dev.rtcoder.fetchmunk.backend', info_plist={'LSBackgroundOnly': True})
