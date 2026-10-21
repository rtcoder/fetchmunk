# History Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the 1000-job ceiling without retaining the full history in Python or Swift memory.
**Architecture:** Indexed SQLite schema 2 with counters; WAL read transactions provide keyset snapshots. Swift keeps one page and the current transfer, and uses global summaries.
**Tech Stack:** Existing Python/sqlite3 and SwiftUI only.
**Spec:** docs/superpowers/specs/2026-10-21-history-scaling-design.md

## Global Constraints

- Pages <=100 records and frames <=1 MiB. Four snapshots, TTL60s, WAL intervention threshold64MiB.
- Preserve jobs, operations, attempts and downloaded files. Backup before schema1 migration.
- No authentication, additional engines, cloud, platform expansion or public distribution.
- Existing macOS13 target, arm64 local .app and DMG; source worktree preserved.

## Review Focus

- Failed migration/backup and malformed existing records must not leave partially upgraded data.
- Reverse paging with a byte-limited page must not skip records; cursors cannot cross snapshots/filters.
- Expired snapshots and held readers must not grow WAL indefinitely or block cancellation.
- Out-of-order UI replies and event gaps must not mix filters, accumulate jobs or overwrite newer state.
- Retry during history navigation must retain FIFO, attempt history and operation idempotency.

## Task 1: Indexed store and migration

**Files:** backend/src/fetchmunk_backend/store.py; backend/tests/test_store.py, test_history_store.py.
**Interfaces:** JobStore.summary() -> dict counts; has_jobs() -> bool; next_queued() -> dict|None; recover_interrupted() bounded batches; save_job() maintains indexed fields and transactional counters.
- [ ] Tests: schema1 fixture backup/preservation, rollback with invalid JSON, FIFO updates/retry, counters rollback and >1000 records. Run pytest and observe missing behavior FAIL.
- [ ] Implement transaction migration, private backup, upsert, indexes/counters and indexed recovery.
- [ ] Run store tests PASS and commit.

## Task 2: SQLite snapshots and service

**Files:** backend/src/fetchmunk_backend/{snapshots,service}.py; backend/tests/{test_snapshots,test_service}.py.
**Interfaces:** SnapshotStore.create(store, at_seq, limit=100, filter='all', anchor=None); page(cursor, limit=100, filter=None); maintain(store); close(). Results include both cursors, snapshot_id, at_seq, jobs. Service adds jobs.summary and paged_jobs capability.
- [ ] Tests for stable snapshot, backwards/byte paging, equal timestamps, TTL/eviction, invalid cursor/filter, WAL invalidation, service summary and >1000 jobs. Run FAIL.
- [ ] Implement signed keyset cursors, independent WAL readers, expiry/cleanup, summary, indexed scheduler. Remove history ceiling.
- [ ] Full backend suite PASS; commit.

## Task 3: Bounded Swift UI

**Files:** macos/Sources/Fetchmunk/{AppModel,BackendClient,MainView,ProtocolModels}.swift; new HistoryModel.swift; macos/Tests/FetchmunkTests/HistoryTests.swift.
**Interfaces:** History state owns rows<=100, cursors, generation, stale flag. AppModel loads one page, refreshes summaries and active job, navigates with cursors; checks paged_jobs before initialize. Backend protocol abstraction permits controlled async replies in tests.
- [ ] Tests: bounded page replacement, stale revision, filter/generation race, global counts, expired cursor fallback and event gap. Run FAIL.
- [ ] Implement state and UI buttons Nowsze/Starsze; pinned active transfer; refresh notice, preserving older pages during changes.
- [ ] Swift suite PASS and commit.

## Task 4: Scale verification and bundle

**Files:** scripts/benchmark_history.py; docs/verification/history-scaling.md; README.md; protocol/spec status.
- [ ] Run controlled 1000/100000 record cases: page latency, initialize/cancel responsiveness, memory, query plans and preserved data. Record actual measurements, not assumed targets.
- [ ] Full Python/Swift tests, build_macos, smoke_bundle, codesign, diff check.
- [ ] Native UI exercise page navigation and pinning using isolated test data; never seed the user's database.
- [ ] Review diff against f30b526 using fresh reviewer, resolve important findings with regression tests, update report and commit.
