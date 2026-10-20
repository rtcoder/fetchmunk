from PyInstaller.utils.hooks import collect_submodules, collect_data_files
from pathlib import Path
root = Path(SPECPATH).parent
hidden = collect_submodules('gallery_dl')
a = Analysis([str(root/'backend/src/fetchmunk_backend/__main__.py')],
             pathex=[str(root/'backend/src')],
             datas=collect_data_files('gallery_dl') + collect_data_files('certifi'),
             hiddenimports=hidden, excludes=['pytest','requests_mock','yt_dlp','tkinter'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='fetchmunk-backend',
          console=True, target_arch='arm64')
coll = COLLECT(exe, a.binaries, a.datas, name='fetchmunk-backend')
