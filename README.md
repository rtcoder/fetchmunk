# Fetchmunk

Native desktop downloads powered by gallery-dl. Paste a link, download, open your files.

## Current status

A working **local macOS Apple Silicon build** is implemented in SwiftUI with a bundled Python backend. The `.app` includes Python, gallery-dl and its dependencies; end users do not install a runtime or use a terminal.

Implemented: public downloads, persistent queue/history, file counters and per-file
progress when available, cancellation, retry, directory selection, opening downloaded
files, restart recovery and readable errors. Only one download worker runs at a time.
A restarted queue requires an explicit resume.

History supports literal text searches over the displayed URL and output directory,
with active, completed, failed and cancelled filters and independent global counters.
Job details show timestamps, attempts and transfer information when available;
the explicitly copied diagnostic report excludes URLs, local paths and filenames.
The interface has system/light/dark appearance and a configurable default directory.
Per-file progress does not imply a known percentage for the whole gallery.

This is not a public release: no Developer ID/notarization, automatic updates or authentication UI. History is paged in groups of up to 100 records, with a separate current-transfer view and global counters. The 1000-job ceiling has been removed; a 100,000-record database is covered by the scale benchmark. Windows/Linux UI is not implemented. C#/Avalonia remains the selected direction for those platforms. The current backend uses Unix process locking and needs a Windows portability pass.

Existing schema-1 databases are backed up to `state-before-v2.sqlite` in the application data directory before the transactional schema-2 migration. Older builds cannot open schema 2; keep the backup if you need to roll back.

## Local artifacts

- `dist/Fetchmunk.app`
- `dist/Fetchmunk-local-arm64.dmg` (drag the application to Applications)

Both are generated, ignored by Git and signed ad hoc. The target is macOS 13+. Native GUI execution has been checked on macOS 27.0.1; packaged backend smoke tests also pass on the macOS 15 arm64 Actions runner. macOS 13 itself remains unverified. Do not treat the local DMG as a notarized public installer.

## Build and test — developers only

Requires Apple Silicon macOS, Xcode command-line tools, and `uv`.

```sh
scripts/bootstrap.sh
PYTHONPATH=backend/src backend/.venv/bin/pytest backend/tests -q
swift test --package-path macos
scripts/build_macos.sh
python3 scripts/smoke_bundle.py --app dist/Fetchmunk.app
backend/.venv/bin/python -m unittest discover -s scripts/tests -v
```

The bootstrap uses Python 3.13.16 from python-build-standalone; dependency hashes are locked in `backend/requirements.lock`. Versions and runtime provenance are recorded in `packaging/toolchain.json`. The build rejects Mach-O deployment targets newer than macOS 13.

The app also contains `build-manifest.json`, `THIRD_PARTY_NOTICES.txt` and available
license texts under `Contents/Resources`. They are generated from the runtime
collection inventory and installed package metadata. Missing license texts are
reported explicitly. Native/vendored components still need review, and the project
license remains undecided; this is not a completed redistribution audit.

## GitHub Actions installers

[Build desktop installers](.github/workflows/build-desktop.yml) runs on a pushed
`v*` tag and can also be started manually from the Actions tab. The macOS job
uses an Apple Silicon `macos-15` runner, installs the pinned uv version and
locked Python dependencies, runs both test suites, builds the app/DMG, and
smoke-tests the app both directly and from the mounted read-only disk image.

Download the DMG and its SHA-256 file from the run's **Artifacts** section
(retained for 30 days). Tag builds use `Fetchmunk-vX.Y.Z-macos-arm64.dmg`;
manual branch builds include `dev-<commit>` in the filename. Tags must follow
`vX.Y.Z` or `vX.Y.Z-prerelease`, with the numeric version matching
`CFBundleShortVersionString` in `packaging/Info.plist`.

The workflow produces ad hoc signed builds, without Developer ID or notarization,
and does not create GitHub Releases. It needs no signing secrets. Windows and
Linux packaging will be added as separate jobs when those clients are ready.
The existing `v0.1.0` tag predates the workflow; it will not trigger a build
retroactively. Use a manual run to test the workflow without moving that tag.

## Documentation

- [Alpha 0.2.0: verification](docs/verification/alpha-0.2.0.md)
- [50-task plan and completion](docs/superpowers/plans/2026-10-21-next-50.md)

- [Installation and release checklist](docs/release.md)
- [History scaling: verification](docs/verification/history-scaling.md)
- [First build: verification and limitations](docs/verification/first-build.md)
- [MVP design](docs/design/mvp.md)
- [GUI–backend protocol](docs/design/protocol-v1.md)
- [Implementation plan](docs/superpowers/plans/2026-10-20-macos-first-build.md)

The design describes the broader target. The verification report records what actually works in this build.

### Alfa 0.3.0

- „Wiele linków…” / ⌘⇧L: do 100 adresów, walidacja, dokładna deduplikacja
  i atomowe dodanie paczki. Ponowienie po utracie odpowiedzi zachowuje identyfikator operacji.
- „Sprawdź”: lokalne rozpoznanie wzorca adresu przez gallery-dl, bez pobierania.
  Nie potwierdza dostępności plików ani uprawnień.
- Dokładniejsze rozróżnienie typowanych błędów uwierzytelniania, HTTP 403 i sieci.

Plan kolejnych 150 zadań: `docs/superpowers/plans/2026-10-21-next-150.md`.
Pierwszy etap obejmuje 0.3.0; pozostałe zadania są roadmapą. Logowanie,
podpis Developer ID/notaryzacja, aktualizator oraz GUI Windows/Linux nadal nie są gotowe.

### Alfa 0.4.0 — poświadczenia i wideo

- Dodatkowy silnik yt-dlp dla YouTube/CDA; automatyczny wybór najlepszej dostępnej
  jakości oraz łączenie obrazu i dźwięku. FFmpeg/Deno są dołączone do aplikacji.
- Okno „Logowanie do serwisów”: CDA login/hasło, cookies z wybranej przeglądarki
  po zgodzie lub pliku Netscape; lista, zastępowanie i usuwanie, bez ujawniania hasła.
- AES-256-GCM; losowy klucz w natywnym magazynie systemowym. Brak plaintext fallback.
- Klucz utracony/uszkodzony rekord: trzeba podać dane ponownie. Odmowa dostępu
  do magazynu nie kasuje danych. Worker musi chwilowo odszyfrować poświadczenia;
  nie jest to system „zero knowledge”, ani ochrona przed przejęciem działającego procesu.
- Bez automatycznego obcinania subdomen: przygotowany rejestr jawnych aliasów jest
  pusty do czasu otrzymania i weryfikacji rzeczywistych przykładów.

Katalogi ekstraktorów i przykładowych adresów: `docs/sources/` (JSON i TXT).
Ograniczenia platform: `docs/security/browser-access-platforms.md`.
Nie sprawdzono kont użytkownika, rzeczywistych materiałów CDA Premium ani profili
przeglądarek. Windows/Linux mają kontrakty/adaptery, ale nie gotowe GUI/buildy.
