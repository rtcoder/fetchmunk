# Fetchmunk

Native desktop downloads powered by gallery-dl. Paste a link, download, open your files.

## Current status

A working **local macOS Apple Silicon build** is implemented in SwiftUI with a bundled Python backend. The `.app` includes Python, gallery-dl and its dependencies; end users do not install a runtime or use a terminal.

Implemented: public downloads, persistent queue/history, file counters and per-file progress when available, cancellation, retry, directory selection, opening downloaded files, restart recovery and readable errors. Only one download worker runs at a time. A restarted queue requires an explicit resume.

This is not a public release: no Developer ID/notarization, automatic updates or authentication UI. History is paged in groups of up to 100 records, with a separate current-transfer view and global counters. The 1000-job ceiling has been removed; a 100,000-record database is covered by the scale benchmark. Windows/Linux UI is not implemented. C#/Avalonia remains the selected direction for those platforms. The current backend uses Unix process locking and needs a Windows portability pass.

Existing schema-1 databases are backed up to `state-before-v2.sqlite` in the application data directory before the transactional schema-2 migration. Older builds cannot open schema 2; keep the backup if you need to roll back.

## Local artifacts

- `dist/Fetchmunk.app`
- `dist/Fetchmunk-local-arm64.dmg` (drag the application to Applications)

Both are generated, ignored by Git and signed ad hoc. The target is macOS 13+, but actual execution has only been verified on macOS 27.0.1. Do not treat the local DMG as a notarized public installer.

## Build and test — developers only

Requires Apple Silicon macOS, Xcode command-line tools, and `uv`.

```sh
scripts/bootstrap.sh
PYTHONPATH=backend/src backend/.venv/bin/pytest backend/tests -q
swift test --package-path macos
scripts/build_macos.sh
python3 scripts/smoke_bundle.py --app dist/Fetchmunk.app
```

The bootstrap uses Python 3.13.16 from python-build-standalone; dependency hashes are locked in `backend/requirements.lock`. Versions and runtime provenance are recorded in `packaging/toolchain.json`. The build rejects Mach-O deployment targets newer than macOS 13.

## Documentation

- [History scaling: verification](docs/verification/history-scaling.md)
- [First build: verification and limitations](docs/verification/first-build.md)
- [MVP design](docs/design/mvp.md)
- [GUI–backend protocol](docs/design/protocol-v1.md)
- [Implementation plan](docs/superpowers/plans/2026-10-20-macos-first-build.md)

The design describes the broader target. The verification report records what actually works in this build.
