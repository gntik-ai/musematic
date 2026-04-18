# Tasks: Generic S3 Storage — Remove MinIO Hard Dependency

**Branch**: `057-generic-s3-storage`
**Input**: Design documents from `specs/057-generic-s3-storage/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4 from spec.md)
- Exact file paths in every description

---

## Phase 1: Setup

No new project infrastructure required — this is a brownfield configuration refactor with no new dependencies, no new data stores, and no new endpoints.

---

## Phase 2: Foundational — Python Config (Blocking Prerequisite)

**Purpose**: Rename `MinIOSettings` → `ObjectStorageSettings` with `S3_*` env prefix and backward-compat `MINIO_*` aliases. Every subsequent task depends on the renamed `settings.s3.*` attribute path.

**⚠️ CRITICAL**: All user story work (Phase 3–4) is blocked until this phase is complete.

- [x] T001 Rename class `MinIOSettings` → `ObjectStorageSettings` and change `env_prefix` from `"MINIO_"` to `"S3_"` in `apps/control-plane/src/platform/common/config.py` (line 85)
- [x] T002 Replace `ObjectStorageSettings` fields in `apps/control-plane/src/platform/common/config.py`: rename `endpoint` → `endpoint_url` (default `""`); drop `default_bucket` and `use_ssl`; add `region: str = "us-east-1"`, `bucket_prefix: str = "platform"`, `use_path_style: bool = True`, `provider: str = "generic"`
- [x] T003 Rename `PlatformSettings.minio: MinIOSettings` → `PlatformSettings.s3: ObjectStorageSettings` (field declaration and `Field(default_factory=...)`) in `apps/control-plane/src/platform/common/config.py`
- [x] T004 Update `_expand_flat_settings` in `apps/control-plane/src/platform/common/config.py`: add `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_BUCKET_PREFIX`, `S3_USE_PATH_STYLE`, `S3_PROVIDER` primary mappings to `("s3", ...)` keys; keep `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` as backward-compat aliases pointing to the same `("s3", ...)` targets; remove `MINIO_DEFAULT_BUCKET` and `MINIO_USE_SSL`; rename `MINIO_BUCKET_DEAD_LETTERS` alias to `S3_BUCKET_DEAD_LETTERS` (keep old key as additional alias)
- [x] T005 Replace `MINIO_*` properties on `PlatformSettings` with `S3_*` equivalents (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_BUCKET_PREFIX`, `S3_USE_PATH_STYLE`, `S3_PROVIDER`) in `apps/control-plane/src/platform/common/config.py`

**Checkpoint**: `S3_ENDPOINT_URL=http://test:9000 python -c "from platform.common.config import PlatformSettings; s=PlatformSettings(); assert s.s3.endpoint_url == 'http://test:9000'"` passes. Also verify `MINIO_ENDPOINT=http://test:9000` resolves to `s.s3.endpoint_url == 'http://test:9000'` via alias (quickstart.md Scenarios 5, 10, 11).

---

## Phase 3: US1 + US2 — P1 Implementation (External S3 + Backward-Compat MinIO)

**Goal**: Update the Python S3 client, rename all internal dict keys, update all Go satellite services, and update Helm charts. Delivers US1 (new external S3 install) and US2 (existing MinIO installs continue unchanged).

**Independent Test (US1)**: Quickstart.md Scenarios 1–4 — client connects with configurable endpoint/region/addressing-style; bucket ops work against local MinIO with `S3_*` env vars.
**Independent Test (US2)**: Quickstart.md Scenarios 5–6 — `MINIO_*` env vars resolve via aliases; `S3_*` takes precedence when both are set.

### Python S3 Client Update

- [x] T006 [US1] Update `AsyncObjectStorageClient.__init__` (lines 40–46) in `apps/control-plane/src/platform/common/clients/object_storage.py`: replace `settings.MINIO_*` references with `settings.s3.*`; make `endpoint_url` conditional (only included in `_client_kwargs` when non-empty); set `region_name` from `settings.s3.region`; set `addressing_style` to `"path"` when `settings.s3.use_path_style` else `"virtual"`; remove `use_ssl` entry (see data-model.md for exact before/after)
- [x] T007 [US4] Update `health_check()` (lines 288–296) in `apps/control-plane/src/platform/common/clients/object_storage.py`: replace `list_buckets()` call with `head_bucket(Bucket=f"{self.settings.s3.bucket_prefix}-agent-packages")`; add `"provider": self.settings.s3.provider` and `"endpoint": self.settings.s3.endpoint_url or "aws-default"` to both success and error response dicts; ensure no credential values appear in any response path (quickstart.md Scenarios 7–9)

### Internal Dict Key Rename (clients["minio"] → clients["object_storage"])

- [x] T008 [P] [US1] Rename all occurrences of `app.state.clients["minio"]` → `app.state.clients["object_storage"]` in `apps/control-plane/src/platform/main.py` (registration at line 161 plus all ~27 dereference sites)
- [x] T009 [P] [US1] Rename `clients["minio"]` → `clients["object_storage"]` in `apps/control-plane/src/platform/execution/dependencies.py` (line 45)
- [x] T010 [P] [US1] Rename `clients["minio"]` → `clients["object_storage"]` in `apps/control-plane/src/platform/evaluation/dependencies.py` (line 48) and `apps/control-plane/src/platform/evaluation/router.py` (lines 117, 179)
- [x] T011 [P] [US1] Rename `clients["minio"]` → `clients["object_storage"]` in `apps/control-plane/src/platform/context_engineering/dependencies.py` (line 46)
- [x] T012 [P] [US1] Rename `clients["minio"]` → `clients["object_storage"]` in `apps/control-plane/src/platform/simulation/dependencies.py` (line 150)
- [x] T013 [P] [US1] Rename `clients["minio"]` → `clients["object_storage"]` in `apps/control-plane/src/platform/registry/dependencies.py` (line 25)
- [x] T014 [P] [US1] Rename `clients["minio"]` → `clients["object_storage"]` in `apps/control-plane/src/platform/testing/dependencies.py`
- [x] T015 [P] [US1] Rename `clients["minio"]` → `clients["object_storage"]` in `apps/control-plane/src/platform/connectors/dependencies.py`
- [x] T016 [P] [US1] Rename `clients["minio"]` → `clients["object_storage"]` in `apps/control-plane/src/platform/fleet_learning/dependencies.py` (line 41)
- [x] T017 [P] [US1] Rename `clients["minio"]` → `clients["object_storage"]` in `apps/control-plane/src/platform/trust/dependencies.py`
- [x] T018 [P] [US1] Rename `clients["minio"]` → `clients["object_storage"]` in `apps/control-plane/src/platform/composition/dependencies.py`

### Go Satellite Services

- [x] T019 [US1] Update `services/runtime-controller/pkg/config/config.go`: rename `MinIOEndpoint` → `S3EndpointURL`, `MinIOBucket` → `S3Bucket`; add `S3AccessKey`, `S3SecretKey`, `S3Region`, `S3UsePathStyle` fields; read `S3_ENDPOINT_URL` first and fall back to `MINIO_ENDPOINT` when empty; apply same fallback pattern for `S3_BUCKET` / `MINIO_BUCKET`; add `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_USE_PATH_STYLE` reads
- [x] T020 [US1] Update `services/runtime-controller/pkg/config/config_test.go`: update test cases for renamed fields; add cases for `S3_ENDPOINT_URL` precedence over `MINIO_ENDPOINT` and for fallback when `S3_ENDPOINT_URL` is unset (quickstart.md Scenarios 13–14)
- [x] T021 [P] [US1] Rename `services/sandbox-manager/internal/artifacts/minio_uploader.go` → `s3_uploader.go` (git mv); rename struct `MinIOUploader` → `S3Uploader`; rename constructor `NewMinIOUploader` → `NewS3Uploader`; retain all HTTP PUT logic unchanged
- [x] T022 [P] [US1] Rename `services/sandbox-manager/internal/artifacts/minio_uploader_test.go` → `s3_uploader_test.go` (git mv); update all `MinIOUploader`/`NewMinIOUploader` references to `S3Uploader`/`NewS3Uploader`
- [x] T023 [P] [US1] Rename `services/simulation-controller/pkg/persistence/minio.go` → `s3_client.go` (git mv); rename struct `MinIOClient` → `S3Client`; rename constructor `NewMinIOClient` → `NewS3Client`; retain all HTTP PUT logic unchanged
- [x] T024 [US1] Update `services/simulation-controller/cmd/simulation-controller/main.go`: change `persistence.NewMinIOClient` → `persistence.NewS3Client`; rename local variable `minio` → `s3Client`; update env-var reads from `MINIO_ENDPOINT` → `S3_ENDPOINT_URL` (with `MINIO_ENDPOINT` fallback); update error message string "MINIO_ENDPOINT is required" → "S3_ENDPOINT_URL is required"
- [x] T025 [US1] Update `services/simulation-controller/cmd/simulation-controller/main_test.go` and `services/simulation-controller/pkg/persistence/persistence_test.go`: replace all `MinIOClient`/`NewMinIOClient` references with `S3Client`/`NewS3Client`

### Helm Charts

- [x] T026 [US2] Add `minio.enabled: true` at the root of `deploy/helm/minio/values.yaml`; this flag preserves existing behavior (true by default) while allowing new installs to set false for external S3
- [x] T027 [US2] Wrap all MinIO deployment templates **except** `secret-platform.yaml` in `{{- if .Values.minio.enabled }}...{{- end }}` in `deploy/helm/minio/templates/` (StatefulSet, Service, PVC, Operator CRDs, existing bucket-init Job, etc.)
- [x] T028 [US1] Update `deploy/helm/minio/templates/secret-platform.yaml` (keep unconditional): rename secret keys `MINIO_ACCESS_KEY` → `S3_ACCESS_KEY`, `MINIO_SECRET_KEY` → `S3_SECRET_KEY`; add `S3_ENDPOINT_URL` entry pointing to the MinIO cluster internal endpoint
- [x] T029 [US1] Create `deploy/helm/minio/templates/bucket-init-job-generic.yaml`: provider-agnostic Kubernetes Job using `amazon/aws-cli` image; creates all 8 platform buckets via `aws s3 mb s3://{prefix}-{name} --endpoint-url $S3_ENDPOINT_URL || true`; add annotations `helm.sh/hook: post-install,post-upgrade` and `helm.sh/hook-weight: "10"`; wrap entire template in `{{- if not .Values.minio.enabled }}`; source credentials and endpoint from the `minio-platform-credentials` Secret
- [x] T030 [US1] Update `deploy/helm/simulation-controller/templates/secret.yaml`: rename `MINIO_ENDPOINT` → `S3_ENDPOINT_URL`, `MINIO_ACCESS_KEY` → `S3_ACCESS_KEY`, `MINIO_SECRET_KEY` → `S3_SECRET_KEY`; update matching keys in `deploy/helm/simulation-controller/values.yaml` to preserve template variable bindings

**Checkpoint (US1+US2)**: After startup, `"object_storage" in app.state.clients` is True and `"minio" not in app.state.clients` is True (quickstart.md Scenario 12). `go test ./...` passes in all three Go service directories.

---

## Phase 4: US3 — Local Developer Stack

**Goal**: Update testdata docker-compose files so developers and CI can use the same `S3_*` env var names against local MinIO that operators use against external providers — zero provider-specific code paths.

**Independent Test**: Start local dev stack; all object-storage-dependent tests pass with `S3_ENDPOINT_URL=http://localhost:9000` and `S3_USE_PATH_STYLE=true` pointing to the MinIO container (quickstart.md Scenario 4).

- [x] T031 [P] [US3] Add `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_BUCKET_PREFIX`, `S3_USE_PATH_STYLE=true` env vars to the platform service in `services/runtime-controller/testdata/docker-compose.yml`; keep the MinIO container entry and its existing `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` vars unchanged
- [x] T032 [P] [US3] Add `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_BUCKET_PREFIX`, `S3_USE_PATH_STYLE=true` env vars to the platform service in `services/sandbox-manager/testdata/docker-compose.yml`; keep the MinIO container entry unchanged

**Checkpoint**: Dev stack starts and all S3 operations resolve via `S3_ENDPOINT_URL=http://localhost:9000` pointing to the local MinIO container.

---

## Phase 5: Polish & Validation

**Purpose**: Verify the vendor-string invariant (FR-011, FR-020) and confirm Go service tests pass.

- [x] T033 Run vendor-string grep check (quickstart.md Scenario 20): `grep -r '"minio"' apps/control-plane/src/ --include="*.py" | grep -v '__pycache__'` must return 0 matches; `grep 'pattern_minio_key' apps/control-plane/src/ -r | wc -l` must be ≥5 (intentional scoped exception per research.md Decision 3)
- [x] T034 [P] Run Go tests for all modified services: `go test ./...` in `services/runtime-controller/`, `services/sandbox-manager/`, `services/simulation-controller/`; confirm Scenarios 13–14 from quickstart.md pass (S3_ENDPOINT_URL precedence + MINIO_ENDPOINT fallback)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 2)**: No dependencies — start immediately. **BLOCKS all user story phases.**
- **US1+US2 (Phase 3)**: Depends on Phase 2 complete.
- **US3 (Phase 4)**: Depends on Phase 2 complete. Can run in parallel with Phase 3.
- **Polish (Phase 5)**: Depends on Phase 3 + Phase 4 complete.

### User Story Dependencies

| Story | Priority | Blocking tasks | Key tasks |
|---|---|---|---|
| US1 | P1 | T001–T005 | T006, T008–T018, T019–T025, T028–T030 |
| US2 | P1 | T001–T005 | T006, T008–T018, T019–T020, T024–T027, T030 |
| US3 | P2 | T001–T005 | T031–T032 |
| US4 | P2 | T001–T005 | T007 |

### Within Phase 3

- T006 → T007 (same file, sequential)
- T008–T018: fully parallel (11 different files)
- T019 → T020 (test after config)
- T021 + T022 can run in parallel with T023 (different services)
- T023 → T024 → T025 (sequential within simulation-controller)
- T026 → T027 (T027 uses the flag defined in T026)
- T028, T029, T030: can run in parallel with T026–T027 (different files)

### Parallel Opportunities

```bash
# Phase 3 — dict rename (all 11 files simultaneously):
Task: T008  main.py
Task: T009  execution/dependencies.py
Task: T010  evaluation/dependencies.py + evaluation/router.py
Task: T011  context_engineering/dependencies.py
Task: T012  simulation/dependencies.py
Task: T013  registry/dependencies.py
Task: T014  testing/dependencies.py
Task: T015  connectors/dependencies.py
Task: T016  fleet_learning/dependencies.py
Task: T017  trust/dependencies.py
Task: T018  composition/dependencies.py

# Phase 3 — Go file renames (parallel pair):
Task: T021  sandbox-manager minio_uploader.go → s3_uploader.go
Task: T023  simulation-controller minio.go → s3_client.go

# Phase 4 — testdata (parallel pair):
Task: T031  runtime-controller testdata/docker-compose.yml
Task: T032  sandbox-manager testdata/docker-compose.yml
```

---

## Implementation Strategy

### MVP First (US1 Only — Unblock External S3 Installs)

1. Complete Phase 2: T001–T005 (config.py)
2. T006 (client init — enables external S3 endpoint)
3. T008 (main.py dict rename — required for startup)
4. T019 (runtime-controller config.go — S3_* env vars)
5. T028–T029 (Helm secret rename + generic bucket-init Job)
6. **STOP and VALIDATE**: Deploy with `minio.enabled=false` against Hetzner Object Storage

### Full Delivery (all four user stories)

1. Phase 2 (T001–T005) — sequential
2. Phase 3 simultaneously:
   - T006, T007 (client file)
   - T008–T018 in parallel (dict rename)
   - T019–T025 (Go services)
   - T026–T030 (Helm)
3. Phase 4 (T031–T032) in parallel with Phase 3
4. Phase 5 (T033–T034) after all above

### Single-Developer Sequence

T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 → T009 → T010 → T011 → T012 → T013 → T014 → T015 → T016 → T017 → T018 → T019 → T020 → T021 → T022 → T023 → T024 → T025 → T026 → T027 → T028 → T029 → T030 → T031 → T032 → T033 → T034

---

## Notes

- `pattern_minio_key` in `fleet_learning/models.py:162` is intentionally **NOT** renamed — requires an Alembic migration which is out of scope (research.md Decision 3)
- `MINIO_USE_SSL` is intentionally dropped — it was silently ignored by aioboto3's `client()` (no `use_ssl` parameter exists); SSL is implicit in the endpoint URL scheme (research.md Decision 4)
- US4 (health observability) is fully delivered by T007 alone; no separate phase is needed
- T008–T018 touch different files and carry no cross-file dependencies — all 11 can be sent to parallel agents in a single message
- All tasks follow format: `- [ ] TXXX [P?] [USN] Description with file path`
