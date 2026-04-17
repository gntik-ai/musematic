# Tasks: Backup and Restore

**Input**: Design documents from `/specs/048-backup-restore/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup — Model Extensions

**Purpose**: Extend shared models and helpers used by every subsequent task. Feature 045 already scaffolded the project; no new project structure is needed.

- [X] T001 Extend `BackupArtifact` with `duration_seconds: float = 0.0` and `BackupManifest` with `schema_version: int = 1` + `total_duration_seconds: float = 0.0`; add `CURRENT_SCHEMA_VERSION = 1` constant in `apps/ops-cli/src/platform_cli/models.py`
- [X] T002 Update `build_artifact()` to accept `duration_seconds: float = 0.0` and pass it to `BackupArtifact` in `apps/ops-cli/src/platform_cli/backup/stores/common.py`
- [X] T003 [P] Update `PostgreSQLBackup.backup()` to measure wall-clock duration (`time.monotonic()`) and pass `duration_seconds` to `build_artifact()` in `apps/ops-cli/src/platform_cli/backup/stores/postgresql.py`
- [X] T004 [P] Update `RedisBackup.backup()` to measure wall-clock duration and pass `duration_seconds` to `build_artifact()` in `apps/ops-cli/src/platform_cli/backup/stores/redis.py`
- [X] T005 [P] Update `QdrantBackup.backup()` to measure wall-clock duration and pass `duration_seconds` to `build_artifact()` in `apps/ops-cli/src/platform_cli/backup/stores/qdrant.py`
- [X] T006 [P] Update `Neo4jBackup.backup()` to measure wall-clock duration and pass `duration_seconds` to `build_artifact()` in `apps/ops-cli/src/platform_cli/backup/stores/neo4j.py`
- [X] T007 [P] Update `ClickHouseBackup.backup()` to measure wall-clock duration and pass `duration_seconds` to `build_artifact()` in `apps/ops-cli/src/platform_cli/backup/stores/clickhouse.py`
- [X] T008 [P] Update `OpenSearchBackup.backup()` to measure wall-clock duration and pass `duration_seconds` to `build_artifact()` in `apps/ops-cli/src/platform_cli/backup/stores/opensearch.py`
- [X] T009 [P] Update `MinIOBackup.backup()` to measure wall-clock duration and pass `duration_seconds` to `build_artifact()` in `apps/ops-cli/src/platform_cli/backup/stores/minio.py`

**Checkpoint**: Model + helper extensions complete — all subsequent store/orchestrator changes can build on these.

---

## Phase 2: Foundational — Kafka Store + Orchestrator Core

**Purpose**: Core infrastructure that MUST be complete before any user story CLI command can work.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T010 Implement `KafkaBackup` store: `backup()` dumps all consumer group offsets to `kafka-offsets.json` via `aiokafka.AIOKafkaAdminClient`; `restore()` commits offsets back; graceful skip if no groups exist in `apps/ops-cli/src/platform_cli/backup/stores/kafka.py` (NEW file)
- [X] T011 Add `BACKUP_ORDER = ["postgresql","qdrant","neo4j","clickhouse","redis","opensearch","kafka","minio"]` and `RESTORE_ORDER` (reversed) class constants; reorder `_stores()` iteration in `create()` to follow `BACKUP_ORDER` and in `restore()` to follow `RESTORE_ORDER` in `apps/ops-cli/src/platform_cli/backup/orchestrator.py`
- [X] T012 Add auto-tag generation (format `backup-{YYYYMMDD-HHMMSS}-{NNN}` when tag is None) and custom-tag validation (regex `^[a-zA-Z0-9_-]+$`, raise `ValueError` early) in `BackupOrchestrator.create()` in `apps/ops-cli/src/platform_cli/backup/orchestrator.py`
- [X] T013 Wire lock acquisition/release into `BackupOrchestrator.create()`: select `KubernetesLock` for k8s mode or `FileLock` for all other modes; lock name `platform-backup-lock`; release in `finally` block; raise on lock failure in `apps/ops-cli/src/platform_cli/backup/orchestrator.py`
- [X] T014 Add Kafka store to `BackupOrchestrator._stores()` (both local and k8s branches); set `manifest.total_duration_seconds` from total elapsed time; write `schema_version` to saved manifest in `apps/ops-cli/src/platform_cli/backup/orchestrator.py`
- [X] T015 Add `schema_version` field persistence to `BackupManifestManager.save()` and `create()`; add schema version compatibility check to `BackupOrchestrator.restore()` (raise `RuntimeError` if manifest version > `CURRENT_SCHEMA_VERSION`) in `apps/ops-cli/src/platform_cli/backup/manifest.py` and `apps/ops-cli/src/platform_cli/backup/orchestrator.py`

**Checkpoint**: Foundation ready — 8-store backup, ordered restore, locking, tagging, and schema versioning all operational.

---

## Phase 3: User Story 1 — Create a Full Platform Backup (Priority: P1) 🎯 MVP

**Goal**: Operator runs `platform-cli backup create` and gets a complete 8-store backup with checksums, progress display, auto-tag, and manifest.

**Independent Test**: Run `platform-cli backup create`; verify 8-store manifest with non-empty checksums and `schema_version: 1` is written to `~/.platform-cli/data/backups/manifests/`.

- [X] T016 [US1] Add `rich.progress.Progress` per-store display (spinner → ✓/✗, elapsed time per store) to `BackupOrchestrator.create()`; suppress when `headless=True` (caller passes flag); update progress on each store completion in `apps/ops-cli/src/platform_cli/backup/orchestrator.py`
- [X] T017 [US1] Add conditional S3/MinIO upload step after local artifacts: if `storage_root` URL starts with `s3://` or `minio://`, upload each artifact with `aioboto3` and update `BackupArtifact.path` to the remote key in `apps/ops-cli/src/platform_cli/backup/orchestrator.py`
- [X] T018 [US1] Update `create_backup()` CLI command: remove `--stores` option, pass `headless=ctx.obj.json_output` to orchestrator, emit per-store status lines in normal mode, emit NDJSON event on completion in `apps/ops-cli/src/platform_cli/commands/backup.py`
- [X] T019 [US1] Extend unit tests for US1: auto-tag format, custom-tag validation rejection, lock acquired/released, Kafka store included in manifest, dependency order verified, duration_seconds populated per artifact in `apps/ops-cli/tests/unit/test_backup.py`

**Checkpoint**: US1 fully functional — `backup create` produces complete 8-store manifest with checksums and correct ordering.

---

## Phase 4: User Story 2 — Restore from a Full Backup (Priority: P1)

**Goal**: Operator runs `platform-cli backup restore <id>` and all stores are restored in reverse dependency order after checksum verification.

**Independent Test**: Create backup, delete data from one store, run `platform-cli backup restore bkp-<id> --yes`, verify deleted data is restored and all other stores are untouched.

- [X] T020 [US2] Add `rich.progress.Progress` per-store restore display to `BackupOrchestrator.restore()`; ensure artifacts are processed in `RESTORE_ORDER` (already wired in T011 but confirm restore path follows it) in `apps/ops-cli/src/platform_cli/backup/orchestrator.py`
- [X] T021 [US2] Update `restore_backup()` CLI command: add `--yes/-y` flag; call `typer.confirm()` with store list when `--yes` is not set; show checksum mismatch error with expected/actual hashes; emit NDJSON event on completion in `apps/ops-cli/src/platform_cli/commands/backup.py`
- [X] T022 [US2] Extend unit tests for US2: restore follows reverse order, checksum mismatch aborts before any store is modified, `--yes` bypasses prompt, schema version > 1 raises error in `apps/ops-cli/tests/unit/test_backup.py`

**Checkpoint**: US2 fully functional — restore verifies checksums, prompts for confirmation, and restores in reverse dependency order.

---

## Phase 5: User Story 3 — List Available Backups (Priority: P1)

**Goal**: Operator runs `platform-cli backup list` and sees a table of all backups sorted newest-first with tag, timestamp, total size, store count, and status.

**Independent Test**: Create two backups with different tags; verify both appear newest-first; run with `--json` flag and verify NDJSON output contains `store_count` and human-readable size.

- [X] T023 [US3] Update `list_backups()` CLI command: add `store_count` (len(manifest.artifacts)) and human-readable total size columns to the Rich table; include tag column (show "auto" if None); emit NDJSON with `store_count` and `total_size_bytes` per item in `apps/ops-cli/src/platform_cli/commands/backup.py`

**Checkpoint**: US3 fully functional — list shows all required metadata columns in both Rich and NDJSON modes.

---

## Phase 6: User Story 4 — Restore a Single Store (Priority: P2)

**Goal**: Operator restores only the corrupted store from a backup without affecting other stores.

**Independent Test**: Create backup, corrupt only Redis, run `platform-cli backup restore bkp-<id> --stores redis --yes`, verify Redis is restored and PostgreSQL is untouched.

- [X] T024 [US4] Add `--stores TEXT` option to `restore_backup()` CLI command: parse comma-separated store names, pass `_parse_stores(stores)` to orchestrator, validate that requested store names exist in the manifest (error with available stores list if not) in `apps/ops-cli/src/platform_cli/commands/backup.py`
- [X] T025 [US4] Extend unit tests for US4: partial restore with `--stores redis` only touches redis store, invalid store name returns error listing available stores in `apps/ops-cli/tests/unit/test_backup.py`

**Checkpoint**: US4 fully functional — single-store restore leaves other stores completely untouched.

---

## Phase 7: User Story 5 — Verify Backup Integrity (Priority: P2)

**Goal**: Operator verifies a backup's checksums without restoring any data.

**Independent Test**: Create backup, corrupt one artifact byte, run `platform-cli backup verify bkp-<id>`, verify exit code 1 and correct store failure reported while others pass.

- [X] T026 [US5] Add `verify_backup(backup_id: str)` subcommand to `backup_app`: calls `orchestrator.restore(backup_id, verify_only=True)`; on success print all-pass summary; on failure print per-store pass/fail table with specific error; exit code 1 on any failure in `apps/ops-cli/src/platform_cli/commands/backup.py`
- [X] T027 [US5] Write unit tests for US5: verify all-pass emits status "completed", checksum mismatch emits per-store failure, missing artifact file emits "file missing" error in `apps/ops-cli/tests/unit/test_backup.py`

**Checkpoint**: US5 fully functional — verify detects corruption and missing artifacts before any restore attempt.

---

## Phase 8: User Story 6 — Automated Scheduled Backups (Priority: P3)

**Goal**: Operator configures the platform to create backups automatically on a schedule with retention-based cleanup.

**Independent Test**: Run `platform-cli backup schedule run-once --retention-days 0`, verify a backup is created and old manifests are pruned.

- [X] T028 [US6] Implement `BackupScheduler` class: `run_once(retention_days: int) -> ScheduledBackupResult` (creates backup, prunes old manifests); `start(cron_expression: str, retention_days: int)` (APScheduler `BlockingScheduler`); `_prune(retention_days: int) -> int` (deletes manifests older than N days, returns count) in `apps/ops-cli/src/platform_cli/backup/scheduler.py` (NEW file)
- [X] T029 [US6] Add `schedule_app = typer.Typer(help="Manage automated backup schedules.")` sub-app; add `schedule start` subcommand with `--cron`, `--retention-days`, `--storage-location` options (blocking); register `schedule_app` on `backup_app` in `apps/ops-cli/src/platform_cli/commands/backup.py`
- [X] T030 [US6] Add `schedule run-once` subcommand to `schedule_app` with `--retention-days`, `--storage-location` options; emits NDJSON event with backup_id and pruned_count in `apps/ops-cli/src/platform_cli/commands/backup.py`
- [X] T031 [US6] Write unit tests for US6: `run_once()` with FakeStore creates manifest and emits result; `_prune()` deletes manifests older than threshold and returns correct count; concurrent lock prevention raises error in `apps/ops-cli/tests/unit/test_backup_scheduler.py` (NEW file)

**Checkpoint**: US6 fully functional — scheduled backups run unattended with retention-based cleanup.

---

## Phase 9: Integration Tests (All User Stories)

**Purpose**: Round-trip tests that exercise the full backup → verify → restore flow without mocking the orchestrator.

- [X] T032 Write `test_full_round_trip`: create backup (8 FakeStores), verify all checksums pass, restore all stores, assert each store's `restore()` was called in reverse order in `apps/ops-cli/tests/integration/test_backup_live.py` (NEW file)
- [X] T033 [P] Write `test_partial_restore`: create backup, restore only `redis` store, assert `redis.restore()` called and `postgresql.restore()` NOT called in `apps/ops-cli/tests/integration/test_backup_live.py`
- [X] T034 [P] Write `test_checksum_failure_aborts_restore`: corrupt one artifact file after backup, assert `RuntimeError` raised during verify phase and no store's `restore()` is called in `apps/ops-cli/tests/integration/test_backup_live.py`
- [X] T035 [P] Write `test_lock_prevents_concurrent_backup`: acquire `FileLock` externally, assert second `orchestrator.create()` raises with "lock could not be acquired" message in `apps/ops-cli/tests/integration/test_backup_live.py`
- [X] T036 [P] Write `test_scheduler_prunes_old_manifests`: create 5 manifests with timestamps older than retention window, run `BackupScheduler._prune(retention_days=1)`, assert all 5 are deleted in `apps/ops-cli/tests/integration/test_backup_live.py`

---

## Phase 10: Polish & Cross-Cutting Concerns

- [X] T037 Update `apps/ops-cli/src/platform_cli/backup/stores/__init__.py` to export `KafkaBackup`; update `apps/ops-cli/src/platform_cli/backup/__init__.py` to export `BackupScheduler`
- [X] T038 Run `ruff check .` and `mypy --strict apps/ops-cli/src/platform_cli/backup/ apps/ops-cli/src/platform_cli/commands/backup.py` from `apps/ops-cli/`; fix all errors including missing type annotations and unreachable imports

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on T001+T002 completing — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Phase 2 complete
- **US2 (Phase 4)**: Depends on Phase 2 + US1 complete (restore needs a backup to restore from)
- **US3 (Phase 5)**: Depends on Phase 2 + US1 complete (list needs manifests)
- **US4 (Phase 6)**: Depends on US2 complete (partial restore reuses full restore path)
- **US5 (Phase 7)**: Depends on US1 complete (verify needs a backup to check)
- **US6 (Phase 8)**: Depends on US1 complete (scheduler calls create)
- **Integration Tests (Phase 9)**: Depends on all US phases complete
- **Polish (Phase 10)**: Depends on all previous phases

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no dependency on other stories
- **US2 (P1)**: Requires US1 (needs a backup to restore from)
- **US3 (P1)**: Requires US1 (needs manifests to list)
- **US4 (P2)**: Requires US2 (partial restore extends full restore)
- **US5 (P2)**: Requires US1 (verify needs a backup to check)
- **US6 (P3)**: Requires US1 (scheduler calls create)

### Within Phase 1 (Setup)

- T001 → T002 (model changes first, then helper update)
- T003–T009 [P] all depend on T002 completing — then run in parallel (7 separate store files)

### Parallel Opportunities

- T003–T009: All 7 existing store duration updates are independent files → fully parallel
- T033–T036: All integration test cases are in the same file but independent test functions → can be written in parallel

---

## Parallel Example: Phase 1 Store Updates

```bash
# After T001 + T002 complete, all store updates run in parallel:
Task: "T003 Update PostgreSQLBackup in backup/stores/postgresql.py"
Task: "T004 Update RedisBackup in backup/stores/redis.py"
Task: "T005 Update QdrantBackup in backup/stores/qdrant.py"
Task: "T006 Update Neo4jBackup in backup/stores/neo4j.py"
Task: "T007 Update ClickHouseBackup in backup/stores/clickhouse.py"
Task: "T008 Update OpenSearchBackup in backup/stores/opensearch.py"
Task: "T009 Update MinIOBackup in backup/stores/minio.py"
```

## Parallel Example: Integration Tests (Phase 9)

```bash
# After T032 establishes the conftest/FakeStore fixtures, parallel:
Task: "T033 Write test_partial_restore in test_backup_live.py"
Task: "T034 Write test_checksum_failure_aborts_restore in test_backup_live.py"
Task: "T035 Write test_lock_prevents_concurrent_backup in test_backup_live.py"
Task: "T036 Write test_scheduler_prunes_old_manifests in test_backup_live.py"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Model extensions (T001–T009)
2. Complete Phase 2: Kafka store + orchestrator core (T010–T015)
3. Complete Phase 3: US1 full backup (T016–T019)
4. **STOP and VALIDATE**: Run `platform-cli backup create`, inspect manifest, verify 8 stores
5. Demo: Full platform backup working end-to-end

### Incremental Delivery

1. Phase 1 + 2 → Core infrastructure ready
2. US1 (T016–T019) → Full backup works → Demo
3. US2 (T020–T022) → Restore works → Demo round-trip
4. US3 (T023) → List works → Demo discovery
5. US4 (T024–T025) → Partial restore → Demo targeted recovery
6. US5 (T026–T027) → Verify → Demo proactive integrity check
7. US6 (T028–T031) → Scheduled → Demo autonomous backups
8. Integration tests + Polish → Ship

---

## Notes

- Feature 045 already provides the scaffolding: `BackupOrchestrator`, 7 store implementations, `KubernetesLock`, `FileLock`, `BackupManifestManager`, and existing unit tests in `tests/unit/test_backup.py`
- The Kafka store (T010) is the only entirely new store — all others are additive modifications
- Removal of `--stores` from `backup create` (spec FR-001): the orchestrator keeps the parameter internally but the CLI does not expose it
- `[P]` tasks in Phase 1 (T003–T009) are the highest-value parallelism opportunity — 7 files with identical patterns
- Integration tests (T032–T036) use the existing `FakeStore` pattern from `test_backup.py` — no live databases needed
