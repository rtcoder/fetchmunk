from PyInstaller.utils.hooks import collect_submodules, collect_data_files, copy_metadata
from pathlib import Path
import json
root = Path(SPECPATH).parent
import deno
hidden = collect_submodules('gallery_dl') + collect_submodules('yt_dlp') + collect_submodules('yt_dlp_ejs') + ['keyring.backends.macOS', 'keyring.backends.macOS.api']
video_data = collect_data_files('yt_dlp_ejs') + collect_data_files('imageio_ffmpeg') + copy_metadata('yt-dlp') + copy_metadata('yt-dlp-ejs')
video_binaries = [(str(Path(deno.find_deno_bin()).resolve()), 'deno-bin')]

a = Analysis([str(root/'backend/src/fetchmunk_backend/__main__.py')],
             pathex=[str(root/'backend/src')],
             datas=collect_data_files('gallery_dl') + collect_data_files('certifi') + video_data,
             binaries=video_binaries,
             hiddenimports=hidden, excludes=['pytest','requests_mock','tkinter'])
# Inventory contains build-local paths only and is never copied into the app.
# Match collected source files to installed dist-info records, including runtime hooks.
(root / 'build' / 'runtime-sources.json').write_text(json.dumps(
    sorted({str(source) for _, source, _ in [*a.pure, *a.binaries, *a.datas, *a.scripts]})))
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='fetchmunk-backend',
          console=True, target_arch='arm64')
coll = COLLECT(exe, a.binaries, a.datas, name='fetchmunk-backend')

app = BUNDLE(coll, name='FetchmunkBackend.app', bundle_identifier='dev.rtcoder.fetchmunk.backend', info_plist={'LSBackgroundOnly': True})
