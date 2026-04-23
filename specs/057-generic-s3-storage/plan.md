# Implementation Plan: Generic S3 Storage — Remove MinIO Hard Dependency

**Branch**: `057-generic-s3-storage` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/057-generic-s3-storage/spec.md`

## Summary

The platform already speaks the generic S3 protocol via `aioboto3` (Python) and raw HTTP PUT (Go sandbox-manager, simulation-controller). MinIO is the only deployment option because the configuration class, internal client dict key, Go struct names, and Helm charts all use `minio`/`MINIO_*` names. This feature replaces those vendor-specific names with generic `s3`/`S3_*` equivalents, makes the MinIO deployment optional in the Helm chart, adds a generic bucket-init Job for external providers, and keeps full backward compatibility so existing `MINIO_*`-configured deployments continue to work without changes.

Total scope: 2 Python source files with targeted edits + 14 Python files with single-line dict-key rename + 7 Go files with targeted edits (including 2 file renames) + 5 Helm chart files (4 modified, 1 new). No Alembic migrations. No new endpoints. No new dependencies.

## Technical Context

**Language/Version**: Python 3.12+ (control plane), Go 1.22+ (satellite services), YAML (Helm charts)
**Primary Dependencies**: aioboto3 (Python S3 client, already present), aws-sdk-go-v2 (Go, already present), botocore (boto3 Config, already present)
**Storage**: No database changes. No new data stores.
**Testing**: pytest + pytest-asyncio 8.x (Python); Go test (Go); manual Helm scenario verification
**Target Platform**: Linux / Kubernetes (same as control plane)
**Project Type**: Brownfield configuration and deployment refactor — no new features or endpoints
**Performance Goals**: No performance impact — identical runtime code paths; only configuration loading changes
**Constraints**: Brownfield Rules 1–8; no file rewrites; no Alembic migrations; MINIO_* env vars must continue to work as aliases for backward compat; `pattern_minio_key` DB column left unchanged (Decision 3)
**Scale/Scope**: 2 significant Python file changes + 14 single-line renames + 7 Go file changes (2 renamed) + 5 Helm files

## Constitution Check

**GATE: Must pass before implementation**

| Principle | Status | Notes |
|---|---|---|
| Modular monolith (Principle I) | ✅ PASS | Changes confined to `common/` (shared infra) + per-bounded-context `dependencies.py` files (dependency injection only) + Go satellite services; no new bounded context coupling |
| No cross-boundary DB access (Principle IV) | ✅ PASS | No DB changes |
| Secrets not in LLM context (Principle XI) | ✅ PASS | `S3_ACCESS_KEY`/`S3_SECRET_KEY` treated identically to existing `MINIO_*` secrets — sourced from K8s Secrets, never from LLM context |
| Generic S3 storage (Principle XVI) | ✅ PASS | This feature directly implements AD-16 |
| Brownfield Rule 1 (no rewrites) | ✅ PASS | All changes are targeted edits; 2 Go files renamed but not rewritten |
| Brownfield Rule 2 (Alembic only) | ✅ PASS | No schema changes; no migrations needed |
| Brownfield Rule 3 (preserve tests) | ✅ PASS | Existing tests continue passing with MINIO_* aliases; new test scenarios added |
| Brownfield Rule 4 (use existing patterns) | ✅ PASS | Follows exact existing settings pattern (env prefix + `_expand_flat_settings`); follows existing dict-based client registration |
| Brownfield Rule 5 (reference existing files) | ✅ PASS | All 23 modified files cited with exact line numbers in data-model.md |
| Brownfield Rule 7 (backward-compatible) | ✅ PASS | MINIO_* env vars kept as aliases in `_expand_flat_settings`; existing deployments unbroken |
| Brownfield Rule 8 (feature flags) | ✅ PASS | `minio.enabled: true` flag in Helm values defaults to true; external S3 is opt-in |
| Critical Reminder 29 (no MinIO in app code) | ✅ PASS | This feature eliminates all MinIO-vendor strings from application code; `pattern_minio_key` column is a scoped exception documented in research.md |

**Post-design re-check**: No violations.

## Project Structure

### Documentation (this feature)

```text
specs/057-generic-s3-storage/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code — What Changes

```text
apps/control-plane/
├── src/platform/
│   ├── common/
│   │   ├── config.py                   MODIFIED — rename MinIOSettings → ObjectStorageSettings,
│   │   │                                           env prefix S3_*, 4 new fields, backward-compat
│   │   │                                           MINIO_* aliases in _expand_flat_settings,
│   │   │                                           rename PlatformSettings.minio → .s3
│   │   └── clients/
│   │       └── object_storage.py       MODIFIED — AsyncObjectStorageClient.__init__:
│   │                                               use settings.s3.*, conditional endpoint_url,
│   │                                               configurable region + addressing_style;
│   │                                               health_check: head_bucket + provider info
│   ├── main.py                         MODIFIED — clients["minio"] → clients["object_storage"]
│   │                                               (line 161 + ~27 dereferences)
│   ├── execution/dependencies.py       MODIFIED — 1 line: clients["minio"] → clients["object_storage"]
│   ├── evaluation/
│   │   ├── dependencies.py             MODIFIED — 1 line
│   │   └── router.py                   MODIFIED — 2 lines (117, 179)
│   ├── context_engineering/
│   │   └── dependencies.py             MODIFIED — 1 line
│   ├── simulation/dependencies.py      MODIFIED — 1 line
│   ├── registry/dependencies.py        MODIFIED — 1 line
│   ├── testing/dependencies.py         MODIFIED — 1 line
│   ├── connectors/dependencies.py      MODIFIED — 1 line
│   ├── fleet_learning/dependencies.py  MODIFIED — 1 line
│   ├── trust/dependencies.py           MODIFIED — 1 line
│   └── composition/dependencies.py     MODIFIED — 1 line
│
services/
├── runtime-controller/
│   ├── pkg/config/config.go            MODIFIED — rename MinIOEndpoint → S3EndpointURL,
│   │                                               MinIOBucket → S3Bucket; add S3AccessKey,
│   │                                               S3SecretKey, S3Region, S3UsePathStyle;
│   │                                               backward-compat fallback to MINIO_*
│   └── pkg/config/config_test.go       MODIFIED — update test cases
├── sandbox-manager/
│   └── internal/artifacts/
│       ├── minio_uploader.go           → s3_uploader.go (RENAMED+MODIFIED — struct + constructor)
│       └── minio_uploader_test.go      → s3_uploader_test.go (RENAMED+MODIFIED — references)
└── simulation-controller/
    ├── cmd/simulation-controller/
    │   ├── main.go                     MODIFIED — NewMinIOClient → NewS3Client, env var reads,
    │   │                                          local var rename, error message strings
    │   └── main_test.go                MODIFIED — references updated
    └── pkg/persistence/
        ├── minio.go                    → s3_client.go (RENAMED+MODIFIED — struct + constructor)
        └── persistence_test.go         MODIFIED — references updated

deploy/helm/
├── minio/
│   ├── values.yaml                     MODIFIED — add minio.enabled: true flag
│   ├── templates/secret-platform.yaml  MODIFIED — keys MINIO_* → S3_*; add S3_ENDPOINT_URL
│   ├── templates/*.yaml (other)        MODIFIED — wrap in {{- if .Values.minio.enabled }}
│   └── templates/
│       └── bucket-init-job-generic.yaml NEW — provider-agnostic; runs when minio.enabled: false
└── simulation-controller/
    ├── templates/secret.yaml           MODIFIED — MINIO_ENDPOINT → S3_ENDPOINT_URL, etc.
    └── values.yaml                     MODIFIED — rename secret keys

testdata/
├── services/runtime-controller/testdata/docker-compose.yml  MODIFIED — S3_* env vars
└── services/sandbox-manager/testdata/docker-compose.yml     MODIFIED — S3_* env vars
```

## Implementation Phases

### Phase 1: Python config class and settings (US1/US2 foundation)

**Goal**: New `ObjectStorageSettings` class with `S3_*` prefix, backward-compat aliases for `MINIO_*`, and renamed `PlatformSettings.s3` field.

**Files**:
- `apps/control-plane/src/platform/common/config.py`:
  1. Rename class `MinIOSettings` → `ObjectStorageSettings`, change `env_prefix="S3_"`
  2. Rename fields: `endpoint` → `endpoint_url`, drop `default_bucket` and `use_ssl`; add `region`, `bucket_prefix`, `use_path_style`, `provider`
  3. Rename `PlatformSettings.minio` → `PlatformSettings.s3`; update type annotation
  4. In `_expand_flat_settings`: add `S3_*` primary mappings, keep `MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY` as aliases pointing to the renamed `s3.endpoint_url/access_key/secret_key`; remove `MINIO_DEFAULT_BUCKET`, `MINIO_USE_SSL`; rename `MINIO_BUCKET_DEAD_LETTERS` → `S3_BUCKET_DEAD_LETTERS` alias key (but keep old key as additional alias)
  5. Replace `MINIO_*` properties on `PlatformSettings` with `S3_*` equivalents

**Independent test**: `S3_ENDPOINT_URL=http://test:9000 python -c "from platform.common.config import PlatformSettings; s=PlatformSettings(); assert s.s3.endpoint_url == 'http://test:9000'"`. Existing `MINIO_ENDPOINT=http://test:9000` also produces the same result via alias.

---

### Phase 2: Python S3 client update (US1/US2)

**Goal**: `AsyncObjectStorageClient` uses `settings.s3.*` properties, supports any S3 provider via configurable endpoint/region/addressing-style, and improves health check.

**Files**:
- `apps/control-plane/src/platform/common/clients/object_storage.py`:
  1. Update `__init__` (lines 40-46): replace hardcoded `MINIO_*` references with `s3.*` settings; make endpoint_url conditional; make region and addressing_style configurable (see data-model.md)
  2. Update `health_check()` (lines 288-296): use `head_bucket` on `{s3.bucket_prefix}-agent-packages`; add `provider` and `endpoint` to response; remove credential values from error output

**Independent test**: Scenario 1–4 and Scenario 7–9 from quickstart.md.

---

### Phase 3: Internal dict key rename (all bounded contexts)

**Goal**: Remove the vendor-specific string `"minio"` from all application code.

**Files**: `main.py` + 13 `dependencies.py`/`router.py` files — all receive the same 1-line change: `clients["minio"]` → `clients["object_storage"]`. See data-model.md Modified Files table for exact lines.

This is a bulk find-and-replace within a clearly bounded pattern. Each file change is 1–2 lines.

**Independent test**: Scenario 12 from quickstart.md — after startup, `"object_storage" in app.state.clients` is True; `"minio" not in app.state.clients` is True.

---

### Phase 4: Go satellite services rename (US1/US2)

**Goal**: Eliminate `MinIO`/`MINIO_` references from all Go service code; keep backward-compat env var fallback.

**Files**:
- `services/runtime-controller/pkg/config/config.go`: rename `Config.MinIOEndpoint` → `Config.S3EndpointURL`, `Config.MinIOBucket` → `Config.S3Bucket`; add `S3AccessKey`, `S3SecretKey`, `S3Region`, `S3UsePathStyle` fields; read `S3_ENDPOINT_URL` first, fall back to `MINIO_ENDPOINT`; same for bucket; update test
- `services/sandbox-manager/internal/artifacts/minio_uploader.go` → `s3_uploader.go`: rename file + struct `MinIOUploader` → `S3Uploader` + constructor `NewMinIOUploader` → `NewS3Uploader`; update test file
- `services/simulation-controller/pkg/persistence/minio.go` → `s3_client.go`: rename file + struct `MinIOClient` → `S3Client` + constructor `NewMinIOClient` → `NewS3Client`; update `main.go` references (local var, constructor call, error messages); update test files

**Independent test**: Scenarios 13–14 from quickstart.md (Go config unit tests). `go test ./...` in each service directory passes.

---

### Phase 5: Helm charts and deployment assets (US1/US2/US3)

**Goal**: MinIO deployment is optional (`minio.enabled: true` default keeps backward compat); simulation-controller secret uses `S3_*` keys; generic bucket-init Job works for any provider.

**Files**:
- `deploy/helm/minio/values.yaml`: add `minio.enabled: true`
- `deploy/helm/minio/templates/secret-platform.yaml`: rename keys `MINIO_ACCESS_KEY` → `S3_ACCESS_KEY`, `MINIO_SECRET_KEY` → `S3_SECRET_KEY`; add `S3_ENDPOINT_URL` entry pointing to the MinIO cluster endpoint
- All other `deploy/helm/minio/templates/*.yaml`: wrap in `{{- if .Values.minio.enabled }}`
- `deploy/helm/minio/templates/bucket-init-job-generic.yaml` (NEW): provider-agnostic Job using `amazon/aws-cli`; creates all 8 platform buckets via `aws s3 mb s3://{prefix}-{name} --endpoint-url $S3_ENDPOINT_URL || true`; runs with annotation `helm.sh/hook: post-install,post-upgrade`; controlled by `{{- if not .Values.minio.enabled }}`
- `deploy/helm/simulation-controller/templates/secret.yaml`: rename `MINIO_ENDPOINT` → `S3_ENDPOINT_URL`, `MINIO_ACCESS_KEY` → `S3_ACCESS_KEY`, `MINIO_SECRET_KEY` → `S3_SECRET_KEY`; update `values.yaml` keys to match
- `services/runtime-controller/testdata/docker-compose.yml` and `services/sandbox-manager/testdata/docker-compose.yml`: add `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` env vars pointing to MinIO container; keep MinIO container

**Independent test**: Scenarios 15–19 from quickstart.md (manual Helm install verification).

---

## API Endpoints Used / Modified

| Endpoint | Status | Change |
|---|---|---|
| `GET /health` (or equivalent health endpoint) | Existing | `object_storage` health section now reports `provider` + `endpoint` in response |

No new endpoints. No other REST API changes.

## Dependencies

- **Feature 004 (MinIO object storage)**: This feature replaces MinIO as the required backend with a generic S3 configuration; MinIO remains as an optional deployment.
- **Feature 013 (FastAPI scaffold)**: `PlatformSettings` and `app.state.clients` dict are the scaffolding targets; no interface change.
- **Feature 009 (Runtime Controller)**: Go config file modified; no gRPC interface change.
- **Feature 010 (Sandbox Manager)**: Go uploader file renamed and struct renamed; no interface change.
- **Feature 012 (Simulation Controller)**: Go client file renamed and struct renamed; no interface change.
- **Feature 045 (Installer)**: Installer script adds `S3_ENDPOINT_URL` collection step (if installer.sh exists in repo — not found in file search; may be handled by Helm install command guidance).

## Complexity Tracking

No constitution violations.

| Category | Count |
|---|---|
| Modified Python source files | 16 (2 significant, 14 single-line) |
| Modified Go source files | 5 (significant edits) |
| Renamed Go files | 4 (2 file renames, each touching 1 associated test) |
| Modified Helm chart files | 4 |
| New Helm chart files | 1 (bucket-init-job-generic.yaml) |
| New Alembic migrations | 0 |
| New REST endpoints | 0 |
| New library dependencies | 0 |
| DB schema changes | 0 |

User input refinements discovered during research:

1. User step 5 references `deploy/helm/platform/values.yaml` which does not exist. Actual Helm targets: `deploy/helm/minio/values.yaml` (toggle) and `deploy/helm/simulation-controller/templates/secret.yaml` (env var rename). Corrected in data-model.md.
2. `MINIO_USE_SSL` was being passed as `use_ssl` to aioboto3 — a parameter that doesn't exist in boto3's `client()` API; it was silently ignored. The field is dropped; SSL is implicit in endpoint URL scheme.
3. Go satellite services (sandbox-manager, simulation-controller) use raw HTTP PUT uploaders, NOT `aws-sdk-go-v2`. They are named `MinIOUploader`/`MinIOClient`. Need renaming to `S3Uploader`/`S3Client`.
4. `app.state.clients["minio"]` appears ~28 times across main.py and ~13 dependencies.py files. User plan step 12 underestimated this scope.
5. `fleet_learning/models.py` has DB column `pattern_minio_key` — left unchanged (no migration scope).
6. User's "Estimated Effort: 2 story points (~1 day)" is accurate for the expanded scope — the changes are mechanical find-and-replace type, just across more files than the user plan identified.
