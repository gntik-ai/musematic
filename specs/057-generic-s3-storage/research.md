# Research: Generic S3 Storage — Remove MinIO Hard Dependency

**Feature**: `specs/057-generic-s3-storage/spec.md`
**Date**: 2026-04-18
**Phase**: 0 — Unknowns resolved, no NEEDS CLARIFICATION markers remain

---

## Decision 1: Python config class rename strategy — `MinIOSettings` → `ObjectStorageSettings`

**Decision**: Rename `MinIOSettings` (env prefix `MINIO_`) to `ObjectStorageSettings` (env prefix `S3_`) in `apps/control-plane/src/platform/common/config.py`. Add new fields (`S3_REGION`, `S3_BUCKET_PREFIX`, `S3_USE_PATH_STYLE`, `S3_PROVIDER`). Drop `MINIO_USE_SSL` (see Decision 4). Keep `MINIO_*` env var names as backward-compat aliases in `_expand_flat_settings` (silent pass-through to the renamed fields) so existing deployments continue reading their configuration without changes.

Rename `PlatformSettings.minio` field → `PlatformSettings.s3`. Add backward-compat properties `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` on `PlatformSettings` as deprecated aliases for `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` so code calling `settings.MINIO_*` still compiles during the transition — they forward to the new `s3.*` sub-settings.

**Rationale**: Brownfield Rule 7 (backward-compatible): renaming env prefix without aliases would break every existing deployment. Keeping MINIO_* aliases in `_expand_flat_settings` means operators can migrate to S3_* on their own schedule; both work simultaneously. Properties on `PlatformSettings` allow any remaining in-code references (e.g., `settings.MINIO_ENDPOINT` call sites) to continue working without touching 30+ call sites — though those are being renamed too (see Decision 2).

**Alternatives considered**: Dropping MINIO_* immediately — rejected; hard cutover for existing deployments. Dual-class (keep MinIOSettings alongside ObjectStorageSettings) — rejected; two sources of truth for the same config.

---

## Decision 2: Internal dict key rename — `app.state.clients["minio"]` → `app.state.clients["object_storage"]`

**Decision**: Rename the string key from `"minio"` to `"object_storage"` in `apps/control-plane/src/platform/main.py` and in all 14 `dependencies.py`/`router.py` files that access `request.app.state.clients["minio"]`. This is ~30 targeted line changes across 15 files; no file is rewritten wholesale (Brownfield Rule 1 respected).

Affected files:
- `main.py:161` (registration) and ~27 further references
- `execution/dependencies.py:45`
- `evaluation/dependencies.py:48`, `evaluation/router.py:117, 179`
- `context_engineering/dependencies.py:46`
- `simulation/dependencies.py:150`
- `registry/dependencies.py:25`
- `testing/dependencies.py`
- `connectors/dependencies.py`
- `fleet_learning/dependencies.py:41`
- `trust/dependencies.py`
- `composition/dependencies.py`

**Rationale**: FR-011 ("Application code MUST NOT contain references to a specific object-storage vendor"). The string `"minio"` is vendor-specific application code. The change is a mechanical find-and-replace confined to the client dict access pattern. Since all occurrences follow the exact same pattern `app.state.clients["minio"]`, the change is safe and low-risk.

**Alternatives considered**: Leaving the internal key as `"minio"` — rejected; violates FR-011 and FR-020 ("no MinIO-vendor strings in application code"). Using a constant like `OBJECT_STORAGE_CLIENT_KEY = "minio"` — rejected; would leave "minio" in application code.

---

## Decision 3: Fleet learning DB column `pattern_minio_key` — leave unchanged

**Decision**: Do NOT rename the `pattern_minio_key` column in `fleet_learning/models.py` (SQLAlchemy `mapped_column`), `fleet_learning/schemas.py` (Pydantic field), or `fleet_learning/transfer.py` (5 references). This column is a historical naming artifact whose value is a generic S3 object key path (e.g., `"fleet-patterns/uuid/pattern.json"`).

**Rationale**: Renaming a DB column requires an Alembic migration. The user plan explicitly states no migrations are needed for this feature. The column stores S3 object key paths — it has no vendor lock-in at the data level. Any sufficiently motivated operator can rename via a trivial migration post-deployment. A name like `pattern_minio_key` is cosmetic noise, not a MinIO dependency. Brownfield Rule 1 also favors the minimal-touch approach.

**Alternatives considered**: Alembic migration renaming `pattern_minio_key` → `pattern_s3_key` — rejected; out of scope per user plan; introduces migration overhead for zero functional benefit.

---

## Decision 4: Drop `MINIO_USE_SSL` / `S3_USE_SSL` — SSL is implicit in endpoint URL scheme

**Decision**: Remove the `use_ssl` field from `MinIOSettings` / new `ObjectStorageSettings`. Do not add a corresponding `S3_USE_SSL` field. In the new `ObjectStorageSettings`, the endpoint URL (`S3_ENDPOINT_URL`) already encodes protocol — `http://` means plain, `https://` means SSL. The `use_ssl` field in `common/clients/object_storage.py` was being passed to aioboto3's `session.client()` as `"use_ssl"`, but aioboto3 does NOT have a `use_ssl` parameter — it was silently ignored by botocore, making it a no-op.

**Rationale**: The field was always a no-op (aioboto3 accepts `verify=False` for disabling cert verification, not `use_ssl=False`). Formalising its removal cleans up dead code. Operators who want HTTP (non-SSL) simply set `S3_ENDPOINT_URL=http://...`; operators who want HTTPS set `S3_ENDPOINT_URL=https://...`.

**Alternatives considered**: Keeping a `S3_VERIFY_SSL: bool = True` flag for cert verification suppression — deferred; operator can set `PYTHONHTTPSVERIFY=0` as a workaround; not needed for MVP. Mapping `MINIO_USE_SSL` to a new `S3_VERIFY_SSL` — rejected; the old field was silently ignored so there's no backward-compat expectation.

---

## Decision 5: Python `object_storage.py` client — make region and addressing style configurable

**Decision**: In `AsyncObjectStorageClient.__init__()` (line 40, `apps/control-plane/src/platform/common/clients/object_storage.py`), replace:
- hardcoded `"region_name": "us-east-1"` → `settings.s3.region` (default `"us-east-1"`)
- hardcoded `s3={"addressing_style": "path"}` → `"path" if settings.s3.use_path_style else "virtual"`
- Remove `"use_ssl"` entry from `_client_kwargs`
- Make `"endpoint_url"` conditional: only pass when `settings.s3.endpoint_url` is non-empty (empty = AWS default)

**Rationale**: These were the only hardcoded MinIO-specific values in the client. Region is required for Hetzner and AWS; path-style is required for MinIO and Hetzner but wrong for AWS. Endpoint URL is optional for AWS S3 (no endpoint needed) but required for all others.

**Alternatives considered**: Keeping hardcoded defaults — rejected; breaks AWS (wrong addressing style) and Hetzner (wrong region). Subclassing for provider — rejected; overkill, one configurable client covers all cases.

---

## Decision 6: Health check improvement — `head_bucket` instead of `list_buckets`

**Decision**: Replace `list_buckets()` with `head_bucket(Bucket=...)` in `AsyncObjectStorageClient.health_check()` (line 288-296, `object_storage.py`). Use the first bucket from the known platform bucket list (e.g., `{settings.s3.bucket_prefix}-agent-packages`). Add `"provider"` and `"endpoint"` fields to the response dict.

**Rationale**: `list_buckets` is restricted or unsupported on some S3 providers (Cloudflare R2, DigitalOcean Spaces require bucket-level permissions only). `head_bucket` against a known bucket is universally supported and directly tests the credential + connectivity path. Response now includes `provider` (from `S3_PROVIDER` — informational label) and `endpoint` (`S3_ENDPOINT_URL` or `"aws-default"`) for operator diagnostics (FR-010, US4).

**Alternatives considered**: Keep `list_buckets` — rejected; fails on R2 and some scoped credentials. Use `get_object` to probe — rejected; creates unnecessary read traffic; `head_bucket` is a lighter check.

---

## Decision 7: Helm chart targets — user plan references `deploy/helm/platform/` which does not exist

**Decision**: The `deploy/helm/platform/` umbrella chart referenced in the user plan does not exist in the codebase. The correct targets are:

**For making MinIO optional (provider-toggle)**:
- `deploy/helm/minio/values.yaml`: Add `minio.enabled: true` flag; wrap all MinIO deployment templates in `{{- if .Values.minio.enabled }}`.
- The runtime-controller gets its S3 credentials via a `configSecretRef` pointing to an external secret (currently `minio-platform-credentials`). Add a generic `s3-platform-credentials` secret template (or extend the minio chart to emit a generic secret when `enabled: false`).

**For per-service S3 config**:
- `deploy/helm/simulation-controller/templates/secret.yaml`: Rename `MINIO_ENDPOINT`/`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` → `S3_ENDPOINT_URL`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`.
- `deploy/helm/runtime-controller/`: No `MINIO_*` keys in configmap or deployment — the credentials come from the externally-referenced secret (`configSecretRef`). No change needed to the Helm template; operators update the secret content.

**For generic bucket init**:
- `deploy/helm/minio/templates/bucket-init-job.yaml`: Existing MinIO-specific init job stays when `minio.enabled: true`.
- Add `deploy/helm/minio/templates/bucket-init-job-generic.yaml` (or a new standalone chart): runs `aws s3 mb` with `--endpoint-url` against any provider; used when `minio.enabled: false`.

**Rationale**: Modifying the existing per-service charts is the brownfield approach. Creating a non-existent umbrella chart would violate Brownfield Rule 1. The simulation-controller chart is the one that needs the most change (it directly embeds MINIO_* in a Secret template).

**Alternatives considered**: Creating `deploy/helm/platform/` umbrella chart — rejected; doesn't exist and creating it is a new bounded deployment artifact; out of scope. Modifying each service Helm chart separately — CORRECT approach.

---

## Decision 8: Go satellite services — rename scope and backward-compat strategy

**Decision**: Three Go services need updates:

**`runtime-controller/pkg/config/config.go`**:
- Add `S3EndpointURL`, `S3Bucket`, `S3AccessKey`, `S3SecretKey`, `S3Region`, `S3UsePathStyle` fields
- Primary env vars: `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_USE_PATH_STYLE`
- Backward-compat: if `S3_ENDPOINT_URL` is empty, fall back to `MINIO_ENDPOINT`; if `S3_BUCKET` is empty, fall back to `MINIO_BUCKET` — same transition pattern as Python
- Remove `MinIOEndpoint` and `MinIOBucket` fields (or rename them — Brownfield Rule 1 says no rewrites; rename = extend; both are acceptable in a struct rename)

**`sandbox-manager/internal/artifacts/minio_uploader.go`** → renamed to `s3_uploader.go`:
- Rename struct `MinIOUploader` → `S3Uploader`
- Rename constructor `NewMinIOUploader` → `NewS3Uploader`
- Retain the raw HTTP PUT logic (it's already endpoint-agnostic)
- Update test file `minio_uploader_test.go` → `s3_uploader_test.go`

**`simulation-controller/pkg/persistence/minio.go`** → renamed to `s3_client.go`:
- Rename struct `MinIOClient` → `S3Client`
- Rename constructor `NewMinIOClient` → `NewS3Client`
- Update `main.go` references from `persistence.NewMinIOClient` → `persistence.NewS3Client`

**Rationale**: FR-011 / FR-020 require no MinIO-vendor strings in application code. The raw HTTP upload logic in sandbox-manager and simulation-controller is already provider-agnostic (plain HTTP PUT to endpoint + bucket + key URL — works with any S3-compatible provider that accepts presigned or authenticated PUT). Only the names are MinIO-specific.

**Alternatives considered**: Rewriting sandbox-manager and simulation-controller to use `aws-sdk-go-v2` — rejected; the raw HTTP logic works correctly and is simpler; switching would be a code rewrite (Brownfield Rule 1). Keeping `MinIOUploader`/`MinIOClient` struct names — rejected; violates FR-011.

---

## Summary: User Plan vs Reality

| User Plan Step | Status | Actual Scope |
|---|---|---|
| 1. Python config: replace `MINIO_*` with `S3_*` | GENUINE + MORE | Rename class, add 4 new fields, keep MINIO_* as aliases, drop use_ssl |
| 2. Python S3 client: update `create_s3_client()` | GENUINE | Modify `__init__` in `AsyncObjectStorageClient` (lines 40-46) |
| 3. Python health check | GENUINE + IMPROVED | Switch to `head_bucket` + add provider/endpoint to response |
| 4. Go config: replace `MINIO_*` env vars | GENUINE | 3 services; also rename struct/file names in sandbox-manager and simulation-controller |
| 5. Helm values: add `objectStorage` section | PATH WRONG | No `deploy/helm/platform/` — target `deploy/helm/minio/values.yaml` + `simulation-controller/templates/secret.yaml` |
| 6. Helm conditional: wrap MinIO deployment | GENUINE | Apply `{{- if .Values.minio.enabled }}` in `deploy/helm/minio/templates/` |
| 7. Bucket init Job | GENUINE | Add generic bucket-init template alongside existing MinIO-specific one |
| 8. S3 Secret | GENUINE | Generic secret template for non-MinIO deployments |
| 9. Installer update | GENUINE (check path) | Need to locate actual installer script |
| 10. .env.example update | GENUINE | Add to testdata docker-compose files too |
| 11. Docker compose | GENUINE | `services/runtime-controller/testdata/docker-compose.yml`, `services/sandbox-manager/testdata/docker-compose.yml` |
| 12. Grep & replace | GENUINE + MORE | `app.state.clients["minio"]` → `"object_storage"` in 15 files; `pattern_minio_key` LEFT UNCHANGED (DB column) |
| 13. Test | GENUINE | Existing tests pass with new S3_* config pointing at local MinIO |
| 14. Integration test | GENUINE | Out of scope for automated tests; documented as manual verification step |
