# Credentials and video implementation plan

User approved autonomous implementation and design choices on 2026-10-25.
Architecture: existing SwiftUI/local Python worker; gallery-dl + pinned yt-dlp.
Spec: this document and docs/security/browser-access-platforms.md (platform evidence).

## Constraints and rulings
- AES-256-GCM, random 32-byte master key in explicit OS secure vault, random nonce,
  authenticated profile context, no plaintext fallback. Losing the master key
  invalidates encrypted profiles; locked/denied/unavailable must preserve them.
- Encryption is reversible; hashing is not. No zero-knowledge promise: the worker
  needs plaintext briefly and Python cannot guarantee memory zeroization.
- No secret read/reveal IPC. UI lists label/service/kind only; replace and remove.
- Credentials never enter jobs/operation journal/logs/argv. Pipe to dedicated worker.
- One profile per service initially, youtube cookies; cda password or cookies.
  Label is user supplied, not a verified account identity. No automatic private profile access.
- Browser opening and importing are explicit UI actions; no bypass of OS/browser
  protections. File import fallback, OS-specific capability/error reporting.
- Video worker authenticates before format discovery, then selects best playable
  non-DRM quality via yt-dlp. User CDA examples pending; no claimed premium validation.
- Bundle video dependencies, never require end-user Python/ffmpeg/JS installation.
- Do not generically strip subdomains. Only verified explicit alias mappings,
  preserve original URL and limit credential scope; initially empty alias registry.
- Export complete extractor IDs/patterns and available canonical example URLs.
  A regex/generic extractor is not a finite exhaustive list of website URLs.

## Tasks
- [x] 1. Official platform research, source inventory and pinned dependencies.
- [x] 2. AES-GCM vault + secure platform key stores; tests loss/tamper/denial.
- [x] 3. yt-dlp isolated adapter, quality selection, worker integration and tests.
- [x] 4. Browser cookie connector + scoped Netscape import, safe errors and tests.
- [x] 5. Auth IPC outside mutation journal; scoped worker handoff; tests no leakage.
- [x] 6. Swift credential list/add/replace/remove, browser selection/open/import.
- [x] 7. Source export files + explicit alias mechanism and tests.
- [x] 8. Bundle dependencies, tests, review, build, smoke and document limitations.

## Review focus
Wrong service credential routing; locked vault mistaken as missing; cookie domain
scope across redirects; callbacks/logs exposing tokens; frozen package missing
native dependencies. Use mocked credentials and localhost, never user sessions.

## Execution result

Completed alpha0.4.0 with 276 tests and local frozen app/video/DMG checks.
Evidence and limitations: docs/verification/alpha-0.4.0.md.
Ruling: credential key stays in explicit OS vault (persistent encryption requires
recoverable key material); no plaintext fallback and no zero-knowledge claim.
Ruling: unreadable GCM record deletion follows user's explicit requirement;
locked/denied preserves data. Cost: a replaced valid key cannot recover old records.
Ruling: no arbitrary subdomain stripping; await concrete examples. Cost: those
unverified localized hosts remain unsupported rather than being silently rewritten.
Ruling: browser import platform policy is conservative; unsupported Windows
Chromium encryption uses file-import fallback. Actual platform acceptance pending.
