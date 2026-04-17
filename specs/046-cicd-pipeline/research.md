# Research: CI/CD Pipeline

**Phase**: Phase 0 — Research  
**Feature**: [spec.md](spec.md)

## Decision 1: Workflow Architecture

**Decision**: Two workflow files — `ci.yml` (quality gates on PRs and main pushes) + `deploy.yml` (release automation on semver tag push). The existing `db-check.yml` is superseded by `ci.yml` and will be deleted. `build-cli.yml` (feature 045) stays separate — it's triggered on `cli-v*` tags and is out of scope for this feature.

**Rationale**: Separating CI from release keeps the concern boundary clean. `ci.yml` runs on every PR — it must not push images or create releases. `deploy.yml` only runs on `v*.*.*` tags. Having two files also allows different permissions (GITHUB_TOKEN write permissions only in deploy.yml). The existing `db-check.yml` is absorbed into `ci.yml` — it already contains the migration check and helm lint patterns; keeping it alongside would create duplicate runs.

**Alternatives considered**:
- Single monolithic workflow with conditional steps — harder to read, permissions must be elevated for all runs
- Reusable workflow files (workflow_call) — adds abstraction with no benefit at this project scale

---

## Decision 2: Path-Based Filtering Strategy

**Decision**: Use GitHub Actions `paths` filter at the job level via `if:` conditions referencing `steps.changes.outputs` from `dorny/paths-filter@v3` action. The filter runs once and all jobs read its output.

**Rationale**: GitHub's native `paths:` filter only works at the workflow level (blocks the whole workflow), not per-job. `dorny/paths-filter` is the standard solution — it runs as a setup job that produces boolean outputs, and each subsequent job checks `if: needs.changes.outputs.{component} == 'true'`. This is the approach used by major GitHub-hosted projects (e.g., rust-lang/rust, grafana/grafana).

**Filter groupings**:
```
python:    apps/control-plane/**
go-reasoning:  services/reasoning-engine/**
go-runtime:    services/runtime-controller/**
go-sandbox:    services/sandbox-manager/**
go-simulation: services/simulation-controller/**
frontend:  apps/web/**
helm:      deploy/helm/**
migrations: apps/control-plane/migrations/**
proto:     services/*/proto/**
docs:      docs/**, *.md, specs/**
```
A `docs`-only change skips all code checks. The `security-scan` job always runs (no path filter).

**Alternatives considered**:
- Separate workflow files per component — too much duplication; can't run all checks on a single PR status page
- Manual `if:` conditions checking `github.event.commits` — brittle and doesn't work well for PRs

---

## Decision 3: Job Concurrency and Ordering

**Decision**: Independent jobs run concurrently with no `needs:` dependency. Only the `security-scan/trivy` step depends on `build-images` completing first (because Trivy scans built images). The `deploy.yml` release jobs are fully sequential: build → push → sbom → release.

**Rationale**: GitHub Actions runs all jobs without `needs:` in parallel by default. For CI, this means lint, typecheck, test, build-images, helm-lint, migration-check, proto-check all run simultaneously — meeting the <10 minute target. For security scanning, `gitleaks` (scans code diff) runs immediately; `trivy` (scans images) needs built images and runs after `build-images`.

**Job DAG for ci.yml**:
```
changes → {lint-python, typecheck-python, test-python, lint-go, test-go,
           lint-frontend, test-frontend, build-images, helm-lint,
           migration-check, proto-check, security-secrets}
build-images → security-trivy
```

---

## Decision 4: Python Quality Tooling

**Decision**: `ruff check` (lint) + `mypy --strict` (type) + `pytest --cov=platform --cov-report=xml --cov-fail-under=95` (test+coverage). Coverage XML is uploaded via `codecov/codecov-action@v4` or stored as a workflow artifact.

**Rationale**: `ruff` and `mypy` are already configured in `apps/control-plane/pyproject.toml`. The `--cov-fail-under=95` flag makes pytest exit non-zero when coverage drops below threshold — the CI job fails automatically with no extra script needed. Coverage XML is standard for PR annotations.

**Working directory**: `apps/control-plane/`  
**Install command**: `pip install -e ".[dev]"`  
**Test run scope**: `pytest` (uses `pyproject.toml` config: `testpaths = ["tests"]`, skips integration tests by default)

---

## Decision 5: Go Quality Tooling

**Decision**: `golangci-lint run` (lint, uses existing `.golangci.yml` per service) + `go test -race -coverprofile=coverage.out ./...` + inline threshold check via `go tool cover -func=coverage.out | awk`.

**Rationale**: Each of the 4 Go services already has `.golangci.yml`. Matrix strategy over services avoids code duplication. Coverage threshold check: `go test` doesn't have a native `--fail-under`; standard approach is `go tool cover -func coverage.out | grep "total:" | awk '{if ($3+0 < 95.0) {print "Coverage "$3" < 95%"; exit 1}}'`.

**Matrix**: `{service: [reasoning-engine, runtime-controller, sandbox-manager, simulation-controller]}`  
**Working directory**: `services/${{ matrix.service }}/`  
**golangci-lint version**: `v1.61+` (latest stable)  
**Go version**: `1.22` (matches go.mod)

---

## Decision 6: Frontend Quality Tooling

**Decision**: `pnpm lint` (ESLint, `--max-warnings=0`) + `pnpm type-check` (tsc --noEmit) + `pnpm test:coverage` (vitest run --coverage). Vitest coverage threshold enforced in `vitest.config.ts` via `coverage.thresholds`.

**Rationale**: `pnpm lint` and `pnpm type-check` are already defined in `apps/web/package.json`. Coverage threshold enforcement requires adding `coverage.thresholds: { lines: 95, branches: 95, functions: 95, statements: 95 }` to `vitest.config.ts` — Vitest exits non-zero when thresholds are not met.

**Package manager**: `pnpm` (detected from `package.json` scripts)  
**Node version**: `20` (LTS, compatible with Next.js 14+)  
**Working directory**: `apps/web/`

---

## Decision 7: Container Image Build Strategy

**Decision**: For PRs, build images with `--load` (no push, stays local) to verify the build succeeds. For main branch and release, build with `--push` to ghcr.io. Images are tagged `sha-{short_sha}` on main and `{semver}-sha-{short_sha}` on release.

**Rationale**: Building without pushing on PRs validates Dockerfiles without consuming registry quota or creating stale images. `docker/build-push-action@v6` supports `push: false` for PR builds. Tagging with SHA ensures traceability. The `docker/metadata-action@v5` generates tags and labels automatically from git context.

**Images to build** (with Dockerfile paths):
| Image | Dockerfile | Context |
|-------|-----------|---------|
| control-plane | `apps/control-plane/Dockerfile` | `apps/control-plane/` |
| web | `apps/web/Dockerfile` | `apps/web/` |
| reasoning-engine | `services/reasoning-engine/Dockerfile` | `services/reasoning-engine/` |
| runtime-controller | `services/runtime-controller/Dockerfile` | `services/runtime-controller/` |
| sandbox-manager | `services/sandbox-manager/Dockerfile` | `services/sandbox-manager/` |
| simulation-controller | `services/simulation-controller/Dockerfile` | `services/simulation-controller/` |

**Note**: `apps/control-plane/Dockerfile` and `apps/web/Dockerfile` do not exist yet — they must be created as part of this feature's implementation.

**Registry**: `ghcr.io/{owner}/{repo}/{image}` (GitHub Container Registry, no external registry account needed)  
**Build cache**: `cache-from: type=gha` + `cache-to: type=gha,mode=max` (GitHub Actions cache)

**Alternatives considered**:
- DockerHub — requires external account/secret management; GHCR is zero-config for GitHub repos
- Kaniko — eliminates Docker daemon but adds complexity; Docker Buildx is simpler for GitHub Actions
- Building all images in one job — loses parallelism; a matrix over images is faster

---

## Decision 8: Helm Validation Approach

**Decision**: Expand the existing `db-check.yml` helm lint pattern to cover all 12 charts in `deploy/helm/`. Run `helm lint deploy/helm/{chart}` for each, then `helm template {chart} | kubeconform` for manifest schema validation.

**Rationale**: The pattern is already proven in `db-check.yml` (postgresql and redis). Kubeconform validates rendered manifests against Kubernetes JSON schemas — catches invalid apiVersions, missing required fields, type mismatches. `--ignore-missing-schemas` allows validation of CRDs without schema files.

**Charts covered** (12): clickhouse, control-plane, kafka, minio, neo4j, opensearch, postgresql, qdrant, reasoning-engine, redis, runtime-controller, simulation-controller.

**Alternatives considered**:
- `helm unittest` — useful but requires test fixtures; not in scope for this feature
- `conftest/OPA policy` — powerful but requires policy authoring; future enhancement

---

## Decision 9: Protocol Buffer Validation

**Decision**: `buf lint` + `buf generate` using the `bufbuild/buf-action@v1` GitHub Action. Each service with proto files gets a `buf.yaml` in its `proto/` directory.

**Rationale**: `buf` is the standard proto toolchain for linting and code generation. `bufbuild/buf-action` handles installation and caching. Currently only `services/reasoning-engine/proto/` has proto files. `buf generate` validates that code generation succeeds — catching import errors and type mismatches that `buf lint` alone won't catch.

**buf.yaml location**: `services/reasoning-engine/proto/buf.yaml` (to be created)  
**buf.gen.yaml location**: `services/reasoning-engine/buf.gen.yaml` (to be created)  
**Lint rules**: `DEFAULT` rule set + `FIELD_LOWER_SNAKE_CASE`

**Alternatives considered**:
- `protoc` directly — requires managing protoc plugins and versions; buf handles this automatically
- Validating only syntax (buf lint without generate) — misses code-gen failures from import changes

---

## Decision 10: Secret Scanning

**Decision**: `gitleaks/gitleaks-action@v2` scans the commit diff on PRs and the full history on first main branch push. Runs as a separate job with no path filter (always executes).

**Rationale**: `gitleaks` is the standard open-source secret scanner for Git repos. The GitHub Action integrates natively with PR context. Scanning the diff (not full history) on PRs keeps execution fast. A `.gitleaks.toml` config file allows allowlisting test fixtures or known-safe patterns.

**Alternatives considered**:
- `truffleHog` — more comprehensive (regex + entropy) but noisier; gitleaks has better false-positive control
- GitHub Advanced Security secret scanning — requires GitHub Enterprise or public repo; gitleaks works on private repos with any GitHub plan

---

## Decision 11: Container Vulnerability Scanning

**Decision**: `aquasecurity/trivy-action@master` scans each built image. Runs after `build-images` completes. Severity filter: `CRITICAL,HIGH`. Reports findings as GitHub Security tab alerts (SARIF format) on main branch; PR comments on pull requests.

**Rationale**: Trivy is the most widely adopted OSS container scanner. The GitHub Action supports SARIF output which integrates with GitHub's Security tab. On PRs, a separate `trivy` step outputs a table summary to the job log — developers see findings immediately without navigating to the Security tab.

**Scan targets**: All 6 images from the build-images job  
**SARIF upload**: `github/codeql-action/upload-sarif@v3` (required for Security tab integration)

**Alternatives considered**:
- Snyk container scanning — requires Snyk account; Trivy is zero-config
- Grype (Anchore) — comparable feature set; Trivy has broader community adoption and better GitHub Actions integration

---

## Decision 12: SBOM Generation and Release Automation

**Decision**: `anchore/sbom-action@v0` generates a CycloneDX JSON SBOM per image during the release workflow. `softprops/action-gh-release@v2` creates the GitHub Release with auto-generated changelog (from PR titles and commit messages) and attaches all SBOM files.

**Rationale**: `anchore/sbom-action` wraps `syft` and natively supports CycloneDX (the SBOM format mandated by most compliance frameworks). `softprops/action-gh-release` is the most feature-complete release action — supports `generate_release_notes: true` which creates a changelog from merged PRs since the last release tag.

**SBOM format**: CycloneDX JSON (compatible with SPDX tooling via converters)  
**Release notes**: Auto-generated from merged PR titles (`generate_release_notes: true`)

**Alternatives considered**:
- `goreleaser` — excellent for Go binaries but not native to Python/Node multi-component repos
- Manual `gh release create` — works but doesn't support SBOM attachment in one step

---

## Decision 13: Caching Strategy

**Decision**:
- **Python**: `actions/setup-python@v5` with `cache: 'pip'` — caches pip download cache
- **Go**: `actions/setup-go@v5` with `cache: true` — caches module download cache and build cache
- **Node/pnpm**: `pnpm/action-setup@v4` + `actions/setup-node@v4` with `cache: 'pnpm'`
- **Docker**: `docker/setup-buildx-action@v3` with GHA cache (`cache-from: type=gha`)

**Rationale**: Each language's setup action has built-in caching that covers the most expensive operation (downloading dependencies). Docker layer caching via GitHub Actions cache reduces image build time significantly for layers that don't change frequently (base image, system packages).

---

## Decision 14: Migration Check Pattern

**Decision**: Reuse the exact pattern from `db-check.yml` — spin up a PostgreSQL service container, run `make migrate`, then `make migrate-check` and grep for branch indicators. This runs in `ci.yml` only when `migrations` path filter is triggered.

**Rationale**: The pattern is already proven and working. The only change is moving it from `db-check.yml` into `ci.yml` as a path-filtered job.
