# Alpha 0.3.0 — verification

Date: 2026-10-21. Target: macOS arm64. Local host: macOS 27.

Implemented: atomic batches of at most 100 input URLs, exact UTF-8 deduplication,
replay after uncertain replies using frozen operation parameters; explicit local
source-pattern inspection; typed extraction error classification.

- Python backend: 154 tests PASS.
- Swift: 41 tests PASS, including frozen batch retry and stale inspection replies.
- Packaging metadata: 4 tests PASS; actionlint and git diff --check PASS.
- Reviewer found Swift canonical Unicode equality collapsing distinct URLs;
  reproduced RED, changed dedupe to UTF-8 Data, regression GREEN.
- Bundled app and read-only mounted DMG smoke: downloads controlled local PNG,
  checks history, metadata, batch replay/deduplication/cancellation, source
  inspection and clean shutdown with PATH=/usr/bin:/bin and temporary user state.

No live website/authentication testing. Source recognition only matches pinned
engine class patterns; it does not prove access or availability. Private gallery-dl
API requires retesting on upgrades. Download-hook failures without typed exceptions
retain generic classification. Pending batch recovery is in-memory for this GUI
session, not persisted across app restart.

Native visual QA of the new sheet was not completed; the prior native capture
failure (ScreenCaptureKit -3811) remains a verification limitation. Compilation
and model/parser tests do not substitute for visual/accessibility acceptance.

Distribution remains ad hoc signed, without Developer ID/notarization. Licenses
are bundled from distributions; complete transitive/native audit is still planned.
Windows/Linux, updater and authentication remain roadmap work.
