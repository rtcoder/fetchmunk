# Alpha 0.4.0 — credentials and video verification

Date: 2026-10-25. macOS arm64 local development build; ad hoc signing.

## Verified

- 220 Python tests,49 Swift tests,7 packaging/source-export tests PASS (276 total).
- actionlint and git diff --check PASS.
- Native Mach-O deployment-target check:9 binaries at or below macOS13.0.
- Packaged app smoke:gallery download, history, atomic batches/idempotency,
  source inspection, metadata and shutdown PASS.
- Frozen video worker smoke: empty PATH, temporary HOME/cwd, controlled localhost
  DASH formats, best-video selection, audio/video merge and decoding by bundled
  FFmpeg PASS. Bundled Deno2.9.8 executes. No external media or credentials used.
- Final read-only mounted DMG runs the same two smoke checks.
- Catalog export is deterministic and socket-disabled:1035 gallery-dl classes,
  1754 yt-dlp classes; IDs/patterns/examples, not a finite exhaustive domain list.

## Review findings and fixes

Fresh reviewer found auth/native prompts blocking the coordinator and host-only
cookies expanding to subdomains. Regression tests reproduced both; fixed with
bounded auth dispatcher, just-in-time vault resolution inside worker, crossprocess
vault transactions and strict cookie policy retaining Netscape/domain flags.
Tests cover cancellation/shutdown while auth waits, refusal of delayed writes,
concurrent saves, cookie headers on root/subdomains and missing-vs-locked keys.

Additional ruling: user explicitly authorized discarding unreadable credentials.
Invalid GCM tag removes only that encrypted record; confirmed missing key removes
unreadable profiles. A different validly formatted key also makes old records
unreadable. No recovery is promised. Locked/denied/unavailable preserves data.

## Limits and remaining acceptance

Native Keychain consent, actual browser profiles, live YouTube and CDA Premium
were NOT exercised. No user credentials were read. Synthetic vault tests use a
fake key store but real AESGCM. Windows/Linux OS adapters and policies exist;
there are no tested Windows/Linux packages or GUIs in this milestone.
Native visual/accessibility acceptance of the new sheet is not completed.
No production signing/notarization or full native/transitive license audit.
GitHub workflow syntax was checked; this version's CI was not dispatched.

CDA user-provided problematic links are pending. We authenticate before discovery
and let yt-dlp choose formats; there is no claim to have reproduced the described
Premium issue. Generic upstream login/expiry messages can remain engine_error when
no reliable typed cause is available. No URL/secret text is exposed for diagnosis.

Browser importing can transiently read a broader cookie database; explicit consent
states this and only allowed service records are saved. Source cookie files remain
outside Fetchmunk and are not deleted. Saved labels are unverified user metadata.
Passwords are encrypted, not hashed. Worker plaintext is unavoidable during use;
Python cannot guarantee memory zeroization or zero knowledge. The master key is
protected by the native OS vault, never a plaintext companion file.

Alias registry intentionally starts empty: no user examples yet and no heuristic
subdomain stripping. Tests pin exact-host matching and preservation of URL parts.
