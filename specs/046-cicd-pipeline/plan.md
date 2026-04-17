# Implementation Plan: CI/CD Pipeline

**Branch**: `046-cicd-pipeline` | **Date**: 2026-04-17 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/046-cicd-pipeline/spec.md`

## Summary

Implement a comprehensive GitHub Actions CI/CD pipeline covering all platform components. The pipeline runs quality gates (lint, type-check, test with ≥95% coverage) for Python, Go (4 services), and TypeScript; builds and validates all 6 container images; runs Helm chart validation, migration chain checks, and proto validation; performs secret and vulnerability scanning. A separate release workflow handles image publishing, SBOM generation, and GitHub Release creation on semver tag push. The existing `db-check.yml` is superseded.

## Technical Context

**Language/Version**: YAML (GitHub Actions workflow syntax) + Python 3.12, Go 1.22, TypeScript 5.x, Dockerfile  
**Primary Dependencies**: GitHub Actions built-in + dorny/paths-filter@v3, golangci/golangci-lint-action@v6, bufbuild/buf-action@v1, gitleaks/gitleaks-action@v2, aquasecurity/trivy-action, anchore/sbom-action@v0, softprops/action-gh-release@v2, docker/build-push-action@v6  
**Storage**: GitHub Container Registry (ghcr.io) for images; GitHub Release assets for SBOMs  
**Testing**: Workflows are tested by pushing branches/tags; see quickstart.md for test scenarios  
**Target Platform**: GitHub Actions runners (ubuntu-latest)  
**Project Type**: CI/CD configuration  
**Performance Goals**: Full pipeline ≤10 min for single-component PR  
**Constraints**: No external registry account needed (GHCR); no external secret management required beyond GITHUB_TOKEN  
**Scale/Scope**: 6 images, 4 Go services (matrix), 1 Python app, 1 frontend, 12 Helm charts, 1 proto service

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Python 3.12+ | PASS | CI uses `python-version: "3.12"` |
| Go 1.22+ | PASS | CI reads `go-version-file: go.mod` |
| ruff lint (Python) | PASS | `lint-python` job |
| mypy --strict (Python) | PASS | `typecheck-python` job |
| pytest ≥95% coverage (Python) | PASS | `test-python` with `--cov-fail-under=95` |
| golangci-lint (Go) | PASS | `lint-go` matrix job |
| go test -race ≥95% coverage (Go) | PASS | `test-go` with inline threshold check |
| ESLint (Frontend) | PASS | `lint-frontend` job |
| TypeScript compilation (Frontend) | PASS | `lint-frontend` runs `tsc --noEmit` |
| helm lint for all modified charts | PASS | `helm-lint` job covers all 12 charts |
| Alembic migration chain integrity | PASS | `migration-check` job |
| No secrets in code (gitleaks) | PASS | `security-secrets` job |
| Proto files compile (buf lint+generate) | PASS | `proto-check` job |

All 13 constitution quality gates are addressed.

## Project Structure

### Documentation (this feature)

```text
specs/046-cicd-pipeline/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── contracts/
│   └── workflow-schemas.md   # Annotated workflow YAML
├── quickstart.md        # Test scenarios and local commands
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code Changes

```text
.github/
└── workflows/
    ├── ci.yml             # NEW: comprehensive quality gate workflow
    ├── deploy.yml         # NEW: release automation workflow
    ├── build-cli.yml      # EXISTING: unchanged (feature 045, out of scope)
    └── db-check.yml       # DELETED: superseded by ci.yml

apps/
├── control-plane/
│   └── Dockerfile         # NEW: multi-stage Python container image
└── web/
    └── Dockerfile         # NEW: multi-stage Next.js container image

services/reasoning-engine/
├── buf.gen.yaml           # NEW: buf code generation config
└── proto/
    └── buf.yaml           # NEW: buf lint rules

apps/web/
└── vitest.config.ts       # MODIFIED: add coverage.thresholds ≥95%

.gitleaks.toml             # NEW: secret scan allowlist config
```

**Structure Decision**: Configuration-as-code — all deliverables are YAML/config files and Dockerfiles. No application source code is modified except `vitest.config.ts` (adding coverage thresholds).

## Implementation Phases

### Phase 1: Prerequisites — Dockerfiles and Config Files

Before `ci.yml` can run image builds, the missing Dockerfiles must be created and proto/buf config must exist.

**Goal**: All 6 images have Dockerfiles; buf is configured; vitest coverage thresholds are set; gitleaks allowlist exists.

**Tasks**:
1. Create `apps/control-plane/Dockerfile` — multi-stage Python image (builder: installs deps; runner: distroless/python or slim)
2. Create `apps/web/Dockerfile` — multi-stage Next.js image (deps → builder → runner with standalone output)
3. Create `services/reasoning-engine/proto/buf.yaml` — buf lint rules (DEFAULT + FIELD_LOWER_SNAKE_CASE)
4. Create `services/reasoning-engine/buf.gen.yaml` — buf code generation (protocolbuffers/go + grpc/go plugins)
5. Modify `apps/web/vitest.config.ts` — add `coverage.thresholds: { lines: 95, branches: 95, functions: 95, statements: 95 }`
6. Create `.gitleaks.toml` — allowlist for test fixtures and spec files

---

### Phase 2: ci.yml — Path Detection and Python Gates (US1)

**Goal**: PRs touching Python code run lint-python, typecheck-python, and test-python. Path filtering is in place for all components.

**Independent test**: Open a PR with a ruff error in `apps/control-plane/`. Verify lint-python fails and blocks merge. Fix it. Verify all Python jobs pass.

**Tasks**:
1. Create `.github/workflows/ci.yml` with workflow header and `changes` job (dorny/paths-filter with all filter groups)
2. Add `lint-python` job (`ruff check .` in `apps/control-plane/`)
3. Add `typecheck-python` job (`mypy src/platform`)
4. Add `test-python` job (pytest + postgres + redis service containers + coverage threshold)

---

### Phase 3: ci.yml — Go Gates (US1)

**Goal**: PRs touching any Go service run lint-go and test-go for that service only (matrix).

**Independent test**: Open a PR touching `services/reasoning-engine/`. Verify lint-go and test-go run for reasoning-engine only. Other Go service matrix rows are skipped.

**Tasks**:
1. Add `lint-go` matrix job (golangci/golangci-lint-action@v6, 4 services)
2. Add `test-go` matrix job (go test -race + coverage threshold script, 4 services)

---

### Phase 4: ci.yml — Frontend Gates (US1)

**Goal**: PRs touching `apps/web/` run lint-frontend and test-frontend with coverage enforcement.

**Independent test**: Open a PR with an ESLint error in `apps/web/`. Verify lint-frontend fails. Fix it; verify test-frontend runs and coverage threshold is enforced.

**Tasks**:
1. Add `lint-frontend` job (pnpm lint + pnpm type-check)
2. Add `test-frontend` job (pnpm test:coverage with vitest thresholds)

---

### Phase 5: ci.yml — Image Builds and Infrastructure (US2)

**Goal**: PRs touching any service or app code trigger image builds. Helm and migration checks run on relevant changes.

**Independent test**: Open a PR touching `services/runtime-controller/`. Verify build-images runs for runtime-controller. Introduce a Dockerfile syntax error; verify the build job fails.

**Tasks**:
1. Add `build-images` matrix job (6 images, `push: false` for PRs, GHA layer cache)
2. Add `helm-lint` job (all 12 charts, helm lint --strict + kubeconform)
3. Add `migration-check` job (postgres service container + make migrate + make migrate-check)

---

### Phase 6: ci.yml — Protocol and Security (US3 + US4)

**Goal**: Proto validation runs on proto file changes. Secret and vulnerability scanning runs on all PRs.

**Independent test**: Add a dummy secret pattern to a test file. Verify security-secrets (gitleaks) fails.

**Tasks**:
1. Add `proto-check` job (bufbuild/buf-action, lint + generate on `services/reasoning-engine/proto`)
2. Add `security-secrets` job (gitleaks/gitleaks-action, no path filter, always runs)
3. Add `security-trivy` job (aquasecurity/trivy-action, depends on build-images, SARIF upload, matrix over 6 images)

---

### Phase 7: deploy.yml — Release Automation (US5)

**Goal**: Pushing a `v*.*.*` tag builds all images, pushes to GHCR, generates SBOMs, and creates a GitHub Release.

**Independent test**: Push `v0.1.0-test` tag. Verify all 6 images appear in GHCR. Verify 6 SBOM files attached to the release. Verify release notes are generated.

**Tasks**:
1. Create `.github/workflows/deploy.yml` with `build-and-push` matrix job (docker/login + metadata + build-push-action with `push: true`)
2. Add `generate-sbom` job (anchore/sbom-action, CycloneDX JSON, per-image matrix)
3. Add `create-release` job (softprops/action-gh-release, download SBOM artifacts, attach files, generate_release_notes: true)

---

### Phase 8: Cleanup and Coverage Optimization (US6)

**Goal**: Delete `db-check.yml` (superseded). Verify path filtering correctly skips jobs. Confirm total pipeline time is under 10 minutes.

**Tasks**:
1. Delete `.github/workflows/db-check.yml`
2. Test documentation-only PR — verify all code jobs are skipped
3. Time a full PR (touching all components) — verify ≤10 min completion

---

## Key Decisions Summary

| Decision | Choice | Reference |
|----------|--------|-----------|
| Path filtering | dorny/paths-filter@v3 per-job | research.md D2 |
| Go quality | golangci-lint-action@v6 + go test -race + awk threshold | research.md D5 |
| Frontend coverage | vitest.config.ts thresholds | research.md D6 |
| Docker builds | build-push-action@v6, no push on PRs | research.md D7 |
| Container registry | ghcr.io (GITHUB_TOKEN, zero config) | research.md D7 |
| Secret scanning | gitleaks/gitleaks-action@v2 | research.md D10 |
| Vuln scanning | trivy-action + SARIF + Security tab | research.md D11 |
| SBOM | anchore/sbom-action CycloneDX JSON | research.md D12 |
| Release | softprops/action-gh-release@v2 | research.md D12 |
| Proto | bufbuild/buf-action@v1 | research.md D9 |
| db-check.yml | Deleted (absorbed into ci.yml) | research.md D1 |
