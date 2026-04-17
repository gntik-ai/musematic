# Data Model: CI/CD Pipeline

**Feature**: [spec.md](spec.md)  
**Note**: This feature produces no database tables. All entities are represented as GitHub Actions artifacts, job outputs, and GitHub API objects. The data model here describes the logical schema of workflow configuration and output artifacts.

---

## Workflow Configuration Entities

### WorkflowTrigger

Defines when a workflow executes.

| Field | Type | Values |
|-------|------|--------|
| `event` | string | `pull_request`, `push`, `push.tags` |
| `branch_filter` | string[] | `["main"]` for push events |
| `tag_filter` | string | `"v*.*.*"` for release |
| `paths_include` | string[] | Component-specific glob patterns |

---

### QualityJob

An individual check within the CI workflow. Maps to a GitHub Actions job.

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Unique job identifier in workflow YAML |
| `name` | string | Human-readable display name |
| `target_component` | string | Component this job validates (e.g., `control-plane`) |
| `path_filter_key` | string | Key in `dorny/paths-filter` output |
| `runs_on` | string | Runner label (e.g., `ubuntu-latest`) |
| `needs` | string[] | Job IDs this job depends on |
| `status` | enum | `queued`, `in_progress`, `success`, `failure`, `skipped`, `cancelled` |
| `duration_seconds` | int | Elapsed time |
| `summary` | string | Result message shown on PR status check |

**Jobs defined in `ci.yml`**:

| job_id | target_component | path_filter_key |
|--------|----------------|-----------------|
| `changes` | — (always runs) | — |
| `lint-python` | control-plane | `python` |
| `typecheck-python` | control-plane | `python` |
| `test-python` | control-plane | `python` |
| `lint-go` | services (matrix) | `go-{service}` |
| `test-go` | services (matrix) | `go-{service}` |
| `lint-frontend` | web | `frontend` |
| `test-frontend` | web | `frontend` |
| `build-images` | all (matrix) | `python OR go-* OR frontend` |
| `helm-lint` | infrastructure | `helm` |
| `migration-check` | control-plane | `migrations` |
| `proto-check` | services | `proto` |
| `security-secrets` | — (no filter) | — (always runs) |
| `security-trivy` | all images | depends on `build-images` |

---

## Pipeline Output Entities

### CoverageReport

Generated per component after test execution.

| Field | Type | Description |
|-------|------|-------------|
| `component` | string | `control-plane`, `reasoning-engine`, etc. |
| `line_coverage_pct` | float | Line coverage percentage (0–100) |
| `branch_coverage_pct` | float | Branch coverage percentage (0–100) |
| `threshold` | float | Minimum required (95.0) |
| `passed` | bool | True if line_coverage_pct ≥ threshold |
| `report_format` | string | `xml` (Python/Go), `json` (Frontend) |
| `artifact_path` | string | Path within workflow artifact store |

---

### ContainerImage

A built container image. Produced by `build-images` job.

| Field | Type | Description |
|-------|------|-------------|
| `service_name` | string | e.g., `control-plane`, `reasoning-engine` |
| `image_ref` | string | Full image reference with tag |
| `short_sha` | string | 7-char git SHA used as tag |
| `semver_tag` | string | Set only on release (e.g., `v1.2.3`) |
| `registry` | string | `ghcr.io/{owner}/{repo}` |
| `build_status` | enum | `success`, `failure` |
| `pushed` | bool | True only on main push and release |
| `dockerfile_path` | string | Path to Dockerfile |

**Image naming convention**: `ghcr.io/{owner}/{repo}/{service_name}:{tag}`  
**Tag formats**:
- PR build: `sha-{short_sha}` (not pushed)
- Main branch: `sha-{short_sha}` (pushed)
- Release: `{semver}` and `sha-{short_sha}` (both pushed)

---

### VulnerabilityFinding

A single security issue found by Trivy image scan.

| Field | Type | Description |
|-------|------|-------------|
| `image` | string | Image reference that was scanned |
| `severity` | enum | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `advisory_id` | string | CVE identifier (e.g., `CVE-2024-12345`) |
| `affected_package` | string | Package name |
| `installed_version` | string | Version currently installed in image |
| `fixed_version` | string | Version that resolves the issue (if available) |
| `report_format` | string | `sarif` (Security tab) or `table` (job log) |

**Reported severities**: CRITICAL and HIGH only (MEDIUM/LOW in log only)

---

### SoftwareBillOfMaterials

Generated per image during release workflow.

| Field | Type | Description |
|-------|------|-------------|
| `image` | string | Image reference |
| `format` | string | `cyclonedx-json` |
| `spec_version` | string | CycloneDX spec version (e.g., `1.5`) |
| `components` | Component[] | List of all packages in the image |
| `generated_at` | ISO8601 | Timestamp of generation |
| `artifact_name` | string | Filename attached to GitHub Release |

---

### ReleaseRecord

The GitHub Release object created by `deploy.yml`.

| Field | Type | Description |
|-------|------|-------------|
| `tag` | string | Semver tag (e.g., `v1.2.3`) |
| `commit_sha` | string | Full git SHA at tag |
| `release_notes` | string | Auto-generated changelog from merged PRs |
| `assets` | string[] | Attached files (SBOM JSON files per image) |
| `container_images` | string[] | Full image references published to GHCR |
| `created_at` | ISO8601 | Publication timestamp |
| `draft` | bool | Always false (published immediately) |
| `prerelease` | bool | True if tag contains `-alpha`, `-beta`, `-rc` |

---

## Path Filter Mapping

The `dorny/paths-filter@v3` step in the `changes` job produces these boolean outputs:

| Output key | Paths watched | Jobs that consume it |
|------------|--------------|---------------------|
| `python` | `apps/control-plane/**` | lint-python, typecheck-python, test-python |
| `go-reasoning` | `services/reasoning-engine/**` | lint-go, test-go (reasoning-engine matrix row) |
| `go-runtime` | `services/runtime-controller/**` | lint-go, test-go (runtime-controller matrix row) |
| `go-sandbox` | `services/sandbox-manager/**` | lint-go, test-go (sandbox-manager matrix row) |
| `go-simulation` | `services/simulation-controller/**` | lint-go, test-go (simulation-controller matrix row) |
| `frontend` | `apps/web/**` | lint-frontend, test-frontend |
| `helm` | `deploy/helm/**` | helm-lint |
| `migrations` | `apps/control-plane/migrations/**` | migration-check |
| `proto` | `services/*/proto/**` | proto-check |
| `images` | `apps/control-plane/**`, `apps/web/**`, `services/**` | build-images, security-trivy |

A PR touching only `docs/**` or `specs/**` produces all outputs as `false` → all code jobs are skipped.
