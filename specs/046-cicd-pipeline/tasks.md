# Tasks: CI/CD Pipeline

**Input**: Design documents from `specs/046-cicd-pipeline/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/workflow-schemas.md ✓, quickstart.md ✓

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)

---

## Phase 1: Setup (Workflow Skeleton Files)

**Purpose**: Create the two workflow files with their scaffolding so subsequent tasks can add jobs to them.

- [X] T001 Create `.github/workflows/ci.yml` — workflow name "CI", triggers (on: pull_request + push branches:[main]), permissions (contents:read, packages:read, security-events:write), empty jobs: {} placeholder
- [X] T002 [P] Create `.github/workflows/deploy.yml` — workflow name "Release", trigger (on: push tags:[v*.*.*]), permissions (contents:write, packages:write, id-token:write), empty jobs: {} placeholder

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All deliverables that must exist before CI can validate them — missing Dockerfiles, buf config, frontend coverage thresholds, and gitleaks allowlist.

**⚠️ CRITICAL**: The `build-images` job in ci.yml will fail without the control-plane and web Dockerfiles. The `proto-check` job requires buf.yaml. The `test-frontend` threshold enforcement requires the vitest.config.ts change.

- [X] T003 [P] Create `apps/control-plane/Dockerfile` — multi-stage Python image: builder stage (python:3.12-slim, COPY pyproject.toml, pip install -e .), runner stage (python:3.12-slim, non-root UID 1000, COPY --from=builder, COPY entrypoints/, ENTRYPOINT ["python", "-m", "uvicorn"])
- [X] T004 [P] Create `apps/web/Dockerfile` — multi-stage Next.js image: deps stage (node:20-alpine, pnpm install --frozen-lockfile), builder stage (pnpm build with output:standalone in next.config.mjs), runner stage (node:20-alpine, non-root UID 1001, COPY --from=builder .next/standalone + .next/static, CMD ["node", "server.js"])
- [X] T005 [P] Create `services/reasoning-engine/proto/buf.yaml` — buf v2 lint config with lint.use: [DEFAULT, FIELD_LOWER_SNAKE_CASE] and breaking.use: [FILE] (see contracts/workflow-schemas.md)
- [X] T006 [P] Create `services/reasoning-engine/buf.gen.yaml` — buf v2 generate config with remote plugins: buf.build/protocolbuffers/go (out: ., opt: paths=source_relative) and buf.build/grpc/go (out: ., opt: [paths=source_relative, require_unimplemented_servers=false])
- [X] T007 [P] Add `coverage.thresholds` to `apps/web/vitest.config.ts` — add to the existing coverage config: thresholds: { lines: 95, branches: 95, functions: 95, statements: 95 }
- [X] T008 [P] Create `.gitleaks.toml` at repo root — allowlist.paths: ["specs", "docs", "apps/web/mocks"], allowlist.regexes: ["dummy|fake|test|example|placeholder"] (see contracts/workflow-schemas.md)

---

## Phase 3: User Story 1 — Validate Code Quality on Every PR (Priority: P1)

**Goal**: All language-specific lint, type-check, and test jobs run automatically on every PR, with ≥95% coverage enforced and path-based filtering so only affected components run.

**Independent Test**: Open a PR with a ruff error in `apps/control-plane/src/`. Verify `lint-python` fails and reports file+line. Fix it. Verify all Python quality jobs pass with coverage summary in the check status. Open a second PR touching only `apps/web/` — verify Go and Python jobs show `skipped` status.

- [X] T009 [US1] Add `changes` job to `.github/workflows/ci.yml` — uses dorny/paths-filter@v3 with 10 filter groups: python (apps/control-plane/**), go-reasoning (services/reasoning-engine/**), go-runtime (services/runtime-controller/**), go-sandbox (services/sandbox-manager/**), go-simulation (services/simulation-controller/**), frontend (apps/web/**), helm (deploy/helm/**), migrations (apps/control-plane/migrations/**), proto (services/*/proto/**), images (apps/control-plane/** + apps/web/** + services/**); outputs all 10 as boolean strings
- [X] T010 [P] [US1] Add `lint-python` job to `.github/workflows/ci.yml` — needs:[changes], if: needs.changes.outputs.python == 'true', runs-on: ubuntu-latest, defaults.run.working-directory: apps/control-plane, steps: checkout + setup-python@v5 (3.12, cache:pip) + pip install -e ".[dev]" + ruff check .
- [X] T011 [P] [US1] Add `typecheck-python` job to `.github/workflows/ci.yml` — needs:[changes], if: needs.changes.outputs.python == 'true', same setup as lint-python, step: mypy src/platform
- [X] T012 [P] [US1] Add `test-python` job to `.github/workflows/ci.yml` — needs:[changes], if: needs.changes.outputs.python == 'true', services: postgres:16 (POSTGRES_DB:musematic, health-cmd:pg_isready, port 5432) + redis:7 (health-cmd:redis-cli ping, port 6379), steps: checkout + setup-python + pip install + pytest --cov=platform --cov-report=xml --cov-fail-under=95 (env: DATABASE_URL, REDIS_TEST_MODE:standalone, REDIS_URL) + upload-artifact (name:python-coverage, path:apps/control-plane/coverage.xml)
- [X] T013 [P] [US1] Add `lint-go` matrix job to `.github/workflows/ci.yml` — needs:[changes], if: any of the four go-* outputs == 'true', strategy.matrix.include: [{service:reasoning-engine,filter:go-reasoning}, {service:runtime-controller,filter:go-runtime}, {service:sandbox-manager,filter:go-sandbox}, {service:simulation-controller,filter:go-simulation}], steps: checkout + setup-go@v5 (go-version-file:services/${{matrix.service}}/go.mod, cache:true) + golangci/golangci-lint-action@v6 (working-directory:services/${{matrix.service}})
- [X] T014 [P] [US1] Add `test-go` matrix job to `.github/workflows/ci.yml` — same matrix as lint-go, defaults.run.working-directory:services/${{matrix.service}}, steps: checkout + setup-go + `go test -race -coverprofile=coverage.out ./...` + coverage threshold awk script (exit 1 if total < 95.0) + upload-artifact (name:go-coverage-${{matrix.service}})
- [X] T015 [P] [US1] Add `lint-frontend` job to `.github/workflows/ci.yml` — needs:[changes], if: needs.changes.outputs.frontend == 'true', defaults.run.working-directory: apps/web, steps: checkout + pnpm/action-setup@v4 + setup-node@v4 (node:20, cache:pnpm, cache-dependency-path:apps/web/pnpm-lock.yaml) + pnpm install --frozen-lockfile + pnpm lint + pnpm type-check
- [X] T016 [P] [US1] Add `test-frontend` job to `.github/workflows/ci.yml` — needs:[changes], if: needs.changes.outputs.frontend == 'true', same setup as lint-frontend, steps: pnpm install + pnpm test:coverage + upload-artifact (name:frontend-coverage, path:apps/web/coverage/)

---

## Phase 4: User Story 2 — Build and Validate Container Images (Priority: P1)

**Goal**: PRs touching any service or app trigger image builds for affected components, verifying they compile and package correctly. Helm charts and migration chains are validated on relevant changes.

**Independent Test**: Open a PR modifying `services/runtime-controller/`. Verify `build-images (runtime-controller)` runs and succeeds. Introduce a syntax error in `services/runtime-controller/Dockerfile`. Verify the build job fails with a clear error. Open a PR modifying `deploy/helm/kafka/`. Verify `helm-lint` runs and validates the chart.

- [X] T017 [US2] Add `build-images` matrix job to `.github/workflows/ci.yml` — needs:[changes], if: needs.changes.outputs.images == 'true', strategy.fail-fast:false, matrix.include: 6 entries [{image:control-plane, dockerfile:apps/control-plane/Dockerfile, context:apps/control-plane}, {image:web, dockerfile:apps/web/Dockerfile, context:apps/web}, {image:reasoning-engine, dockerfile:services/reasoning-engine/Dockerfile, context:services/reasoning-engine}, {image:runtime-controller, ...}, {image:sandbox-manager, ...}, {image:simulation-controller, ...}]; steps: checkout + docker/setup-buildx-action@v3 + docker/metadata-action@v5 (image:ghcr.io/${{github.repository}}/${{matrix.image}}, tags:[type=sha,prefix=sha-]) + docker/build-push-action@v6 (push:false, load:true, cache-from:type=gha, cache-to:type=gha,mode=max)
- [X] T018 [P] [US2] Add `helm-lint` job to `.github/workflows/ci.yml` — needs:[changes], if: needs.changes.outputs.helm == 'true', steps: checkout + azure/setup-helm@v4 + install kubeconform (curl download v0.6.7 linux-amd64, mv to /usr/local/bin) + script: for chart in deploy/helm/*/; do helm dependency build "$chart" 2>/dev/null || true; helm lint "$chart" --strict; helm template release "$chart" | kubeconform -strict -ignore-missing-schemas -kubernetes-version 1.29.0; done
- [X] T019 [P] [US2] Add `migration-check` job to `.github/workflows/ci.yml` — needs:[changes], if: needs.changes.outputs.migrations == 'true', services: postgres:16 (same as test-python), defaults.run.working-directory:apps/control-plane, steps: checkout + setup-python@v5 (3.12, cache:pip) + pip install -e ".[dev]" + make migrate (env:DATABASE_URL) + make migrate-check then grep for "Rev:" exit 1 if found (env:DATABASE_URL)

---

## Phase 5: User Story 3 — Scan for Security Vulnerabilities (Priority: P1)

**Goal**: Every PR is scanned for accidentally committed secrets. Built images are scanned for known critical/high vulnerabilities. Secret scan always runs (no path filter). Trivy results appear in the GitHub Security tab.

**Independent Test**: Create a PR adding `API_KEY = "sk-test-AAAAABBBBBCCCCC12345678901234567"` to any file not in the allowlist. Verify `security-secrets` fails and reports the file and line. Remove the line; verify the job passes.

- [X] T020 [P] [US3] Add `security-secrets` job to `.github/workflows/ci.yml` — no needs/no path-filter (always runs on every PR), steps: checkout@v4 (fetch-depth:0) + gitleaks/gitleaks-action@v2 (env.GITHUB_TOKEN: ${{secrets.GITHUB_TOKEN}})
- [X] T021 [US3] Add `security-trivy` job to `.github/workflows/ci.yml` — needs:[build-images], permissions.security-events:write, strategy.matrix.image: [control-plane, web, reasoning-engine, runtime-controller, sandbox-manager, simulation-controller]; steps: checkout + docker/setup-buildx-action@v3 + docker/build-push-action@v6 (rebuild with load:true, tag:scan-target:${{matrix.image}}, cache-from:type=gha) + aquasecurity/trivy-action@master (image-ref:scan-target:${{matrix.image}}, format:sarif, output:trivy-${{matrix.image}}.sarif, severity:CRITICAL,HIGH, exit-code:"0") + github/codeql-action/upload-sarif@v3 (if:always(), sarif_file:trivy-${{matrix.image}}.sarif, category:trivy-${{matrix.image}})

---

## Phase 6: User Story 4 — Validate Protocol and Interface Definitions (Priority: P2)

**Goal**: PRs touching proto files run buf lint and buf generate to verify syntax, style compliance, and that code generation succeeds.

**Independent Test**: Modify `services/reasoning-engine/proto/reasoning_engine.proto` to add a field name violating FIELD_LOWER_SNAKE_CASE (e.g., `camelCaseField`). Open a PR. Verify `proto-check` fails and reports the violation.

- [X] T022 [US4] Add `proto-check` job to `.github/workflows/ci.yml` — needs:[changes], if: needs.changes.outputs.proto == 'true', steps: checkout@v4 + bufbuild/buf-action@v1 (input:services/reasoning-engine/proto, lint:true, format:true, generate:true)

---

## Phase 7: User Story 5 — Automate Release Deployment (Priority: P2)

**Goal**: Pushing a semver tag triggers a fully automated release: all images built and pushed to GHCR with semver+SHA tags, one SBOM per image in CycloneDX JSON format, and a GitHub Release with auto-generated changelog and attached SBOMs.

**Independent Test**: Push `git tag v0.1.0 && git push origin v0.1.0`. Verify all 6 images appear in GHCR tagged both `v0.1.0` and `sha-{short_sha}`. Verify 6 `sbom-*.cdx.json` files are attached to the GitHub Release. Verify release notes list merged PRs since last tag.

- [X] T023 [US5] Add `build-and-push` matrix job to `.github/workflows/deploy.yml` — strategy.fail-fast:false, same 6-image matrix as ci.yml build-images; steps: checkout@v4 + docker/setup-buildx-action@v3 + docker/login-action@v3 (registry:ghcr.io, username:${{github.actor}}, password:${{secrets.GITHUB_TOKEN}}) + docker/metadata-action@v5 (tags:[type=semver pattern={{version}}, type=sha prefix=sha-]) + docker/build-push-action@v6 (push:true, tags+labels from metadata, cache-from:type=gha, cache-to:type=gha,mode=max)
- [X] T024 [P] [US5] Add `generate-sbom` matrix job to `.github/workflows/deploy.yml` — needs:[build-and-push], strategy.matrix.image: [control-plane, web, reasoning-engine, runtime-controller, sandbox-manager, simulation-controller]; steps: anchore/sbom-action@v0 (image:ghcr.io/${{github.repository}}/${{matrix.image}}:${{github.ref_name}}, format:cyclonedx-json, output-file:sbom-${{matrix.image}}.cdx.json) + actions/upload-artifact@v4 (name:sbom-${{matrix.image}}, path:sbom-${{matrix.image}}.cdx.json)
- [X] T025 [US5] Add `create-release` job to `.github/workflows/deploy.yml` — needs:[generate-sbom], steps: checkout@v4 + actions/download-artifact@v4 (pattern:sbom-*, merge-multiple:true, path:sbom-files/) + softprops/action-gh-release@v2 (generate_release_notes:true, files:sbom-files/*.cdx.json, fail_on_unmatched_files:true)

---

## Phase 8: Polish and Optimization (US6)

**Goal**: Remove the superseded workflow, verify path filtering eliminates unnecessary runs, and confirm the pipeline meets the <10 minute target.

- [X] T026 [US6] Delete `.github/workflows/db-check.yml` — this workflow is fully superseded by `ci.yml` (migration-check, helm-lint, and Redis integration tests are all covered); verify no jobs are lost
- [X] T027 [US6] Verify path filtering completeness in `.github/workflows/ci.yml` — review the `changes` job filter definitions to confirm: docs-only PRs (specs/**, docs/**, *.md) produce all outputs as 'false'; the `images` filter includes all 3 image source roots; each Go matrix row's if-condition checks its specific service output (not a combined OR that would run all 4 for any Go change)

---

## Dependencies

```
T001 (ci.yml skeleton)
├── T009 (changes job)          ← must exist before any job can reference it
│   ├── T010–T016 (Python + Go + Frontend jobs)  ← all check changes outputs
│   ├── T017–T019 (builds + infra)
│   ├── T021 (trivy)            ← needs build-images (T017) too
│   └── T022 (proto)
└── T020 (gitleaks)             ← no changes dependency, runs standalone

T002 (deploy.yml skeleton)
└── T023 → T024 → T025         ← strictly sequential

T003, T004 → T017              ← Dockerfiles must exist before image build job runs
T005, T006 → T022              ← buf.yaml must exist before proto-check job runs
T007 → T016                    ← vitest thresholds must exist before test-frontend job runs
T008 → T020                    ← .gitleaks.toml must exist before gitleaks job runs
```

**Story completion order**: US1 → US2 → US3 (all P1, can be worked in parallel with distinct jobs) → US4 → US5 (P2) → US6 (P3)

---

## Parallel Execution

**Phases 3–6 jobs can be built in parallel** (they all target separate sections of `ci.yml`):

```
Phase 3 US1:  T010, T011, T012, T013, T014, T015, T016  ← all independent jobs
Phase 4 US2:  T017, T018, T019                           ← independent of US1 jobs
Phase 5 US3:  T020, T021                                 ← independent of US1/US2
Phase 6 US4:  T022                                       ← independent of all above
```

**Within Phase 2 (Foundational)**: T003–T008 are all independent (different files) — implement all in parallel.

---

## Implementation Strategy

**MVP scope** (get green CI on next PR): Complete Phases 1–3 (T001–T016)
- This delivers the full US1 quality gate: lint, type-check, and test for all 3 language stacks with coverage enforcement and path filtering.
- A PR opened after T001–T016 are merged will have 8 parallel quality checks running in under 5 minutes.

**Increment 2**: Add Phases 4–5 (T017–T021) — image builds + security scanning
**Increment 3**: Add Phases 6–7 (T022–T025) — proto validation + release automation
**Final**: Phase 8 (T026–T027) — cleanup + verification

---

## Summary

| Phase | Tasks | Story | Parallelizable |
|-------|-------|-------|----------------|
| Setup | T001–T002 | — | T002 [P] |
| Foundational | T003–T008 | — | T003–T008 all [P] |
| US1 Quality Gates | T009–T016 | US1 | T010–T016 [P] |
| US2 Image Builds | T017–T019 | US2 | T018, T019 [P] |
| US3 Security | T020–T021 | US3 | T020 [P] |
| US4 Proto | T022 | US4 | — |
| US5 Release | T023–T025 | US5 | T024 [P] |
| US6 Polish | T026–T027 | US6 | — |
| **Total** | **27** | | **16 parallelizable** |
