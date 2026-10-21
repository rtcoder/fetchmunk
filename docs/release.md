# Local installation and release readiness

## Install a local macOS build

The current artifact targets Apple Silicon and declares macOS 13 as its minimum.
Execution on macOS 13 itself is not yet verified. Open the generated DMG, drag
Fetchmunk into Applications, eject the disk image, then launch the installed app.
Python and gallery-dl are inside the app; no developer environment is required.

Local and Actions artifacts are signed ad hoc, without a Developer ID signature
or notarization. macOS may block downloaded copies. Only open a build whose origin
you trust; this project does not yet provide a notarized public installer.
Do not disable system-wide security protections to install it.

Choose an output folder, paste a public supported URL, and start the download.
Authentication UI, automatic updates and Windows/Linux clients are not implemented.
Live sites can change independently of the application. Synthetic download tests do
not establish compatibility with all gallery-dl extractors.

## Generated bundle records

Every `scripts/build_macos.sh` build creates these files before signing:

- `Contents/Resources/build-manifest.json`: application, Python and gallery-dl
  versions, selected distribution versions, missing license texts and SHA-256 hashes.
- `Contents/Resources/THIRD_PARTY_NOTICES.txt`: inventory and explicit limitations.
- `Contents/Resources/licenses/`: available installed distribution license/notice
  files, plus `Python-LICENSE.txt` from the Python runtime used to freeze the backend.

`packaging/backend.spec` emits a build-only inventory of collected source files.
The generator matches it against `importlib.metadata` file records, so merely
installing pytest in the developer environment does not add it to runtime notices.
PyInstaller runtime hooks are included when collected. The build-only inventory
contains local build paths and is not shipped; generated notices and manifest do
not contain them. No environment variables, user configuration or logs are copied.

Missing distribution license files are listed explicitly rather than fabricated.
The Python license is mandatory. Smoke tests require the manifest and notices,
verify referenced file hashes and compare the running engine version. This detects
missing resources; it does **not** establish legal completeness or redistribution
permission. Native libraries from the Python distribution, vendored components,
and system frameworks still need a separate provenance/license review. Fetchmunk's
own license remains undecided. An empty `missing_license_texts` list only means the
selected distribution metadata supplied text, not that the release audit is done.

## Before a public release

- Choose and document the Fetchmunk project license; review compatibility and
  obligations for gallery-dl and every shipped dependency.
- Review the exact bundle, native libraries and vendored dependencies against
  license texts, attribution, source availability and other applicable obligations.
  Resolve missing texts and the generator's explicit coverage limitations.
- Obtain Developer ID signing, sign the complete nested bundle, notarize and staple;
  validate the downloaded installer on a clean Mac with default security settings.
- Test supported minimum macOS and each advertised CPU architecture. Current builds
  are arm64 only; deployment-target checks are not runtime compatibility tests.
- Test a documented set of live sources, interruptions, failures and output access;
  use dedicated test data and never publish private cookies, URLs or diagnostics.
- Verify migration/rollback, keyboard use and VoiceOver on actual hardware.
- Run Python, Swift and packaging tests; build and smoke-test the app and mounted
  DMG; verify hashes of the final distributed artifact and record exact versions.
- Decide and document update delivery and support policy before promising updates.
