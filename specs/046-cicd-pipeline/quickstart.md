# Quickstart: CI/CD Pipeline

**Feature**: [spec.md](spec.md)

## What This Feature Creates

```text
.github/
└── workflows/
    ├── ci.yml             # PR + main branch quality gate (replaces db-check.yml)
    └── deploy.yml         # Release workflow triggered on v*.*.* tags

apps/
├── control-plane/
│   └── Dockerfile         # NEW: Multi-stage Python image
└── web/
    └── Dockerfile         # NEW: Multi-stage Next.js image

services/reasoning-engine/
├── buf.gen.yaml           # NEW: buf code generation config
└── proto/
    └── buf.yaml           # NEW: buf lint config

apps/web/
└── vitest.config.ts       # MODIFIED: add coverage.thresholds (≥95%)

.gitleaks.toml             # NEW: gitleaks allowlist config
```

Deleted file: `.github/workflows/db-check.yml` (superseded by `ci.yml`)

---

## Running Checks Locally

### Python

```bash
cd apps/control-plane

# Lint
ruff check src/platform entrypoints

# Type check
mypy src/platform

# Tests with coverage
pytest --import-mode=importlib --cov --cov-report=term-missing --cov-fail-under=95
```

### Go (per service)

```bash
cd services/reasoning-engine  # or runtime-controller, sandbox-manager, simulation-controller

# Lint
golangci-lint run

# Race detector
go test -race -coverprofile=coverage.out ./...

# Coverage threshold
# runtime-controller and reasoning-engine exclude generated/bootstrap packages in CI.
go tool cover -func=coverage.out | grep "^total:"
```

### Frontend

```bash
cd apps/web

# Lint + type check
pnpm lint
pnpm type-check

# Tests with coverage
pnpm test:coverage
```

### Helm charts

```bash
# All charts
for chart in deploy/helm/*/; do
  helm lint "$chart" --strict
done
```

### Proto validation

```bash
# From repo root (requires buf CLI)
cd services/reasoning-engine/proto
buf lint
buf generate
```

### Secret scan

```bash
# From repo root (requires gitleaks CLI)
gitleaks detect --source=. --config=.gitleaks.toml
```

---

## Testing the CI Workflows

### Test US1: Quality gate blocks a bad PR

1. Create a branch with a deliberate ruff error (e.g., unused import in any `.py` file in `apps/control-plane/src/`)
2. Open a PR to `main`
3. Verify `lint-python` job fails with the file and line reported
4. Fix the error, push again
5. Verify all Python jobs pass

### Test US2: Image build validates Dockerfile

1. Introduce a syntax error in `apps/control-plane/Dockerfile`
2. Open a PR touching any file in `apps/control-plane/`
3. Verify `build-images (control-plane)` fails
4. Fix the Dockerfile, push again

### Test US3: Secret scan catches committed credential

1. On a test branch, add a line to any file: `API_KEY = "sk-test-AAAAABBBBBCCCCC12345678901234567"`
2. Open a PR
3. Verify `security-secrets` (gitleaks) fails and reports the file
4. Remove the line, push again

### Test US4: Proto check validates buf

1. Modify `services/reasoning-engine/proto/reasoning_engine.proto` to add a field violating buf style rules
2. Open a PR
3. Verify `proto-check` fails
4. Fix the violation

### Test US5: Release creates GitHub Release

1. Ensure `main` branch CI passes
2. Push a semver tag: `git tag v0.1.0 && git push origin v0.1.0`
3. Verify `deploy.yml` runs
4. Verify all 6 images appear in GHCR with `v0.1.0` and `sha-{short_sha}` tags
5. Verify 6 SBOM files are attached to the GitHub Release
6. Verify release notes are auto-generated from merged PRs

### Test US6: Path filtering skips unaffected jobs

1. Open a PR that only changes `apps/web/README.md` (docs-only)
2. Verify `changes` job completes with all code outputs as `false`
3. Verify all code quality jobs show `skipped` status on the PR

---

## Coverage Threshold Enforcement

### Python: automatic via pytest

```bash
# Fails with exit code 2 if coverage < 95%
pytest --cov=platform --cov-fail-under=95
```

### Go: check script (used in ci.yml)

```bash
# Race detector
go test -race ./...

# Coverage profile
# runtime-controller and reasoning-engine build coverage from filtered package lists in ci.yml.
go test ./... -coverprofile=coverage.out
total=$(go tool cover -func=coverage.out | grep "^total:" | awk '{print $3}' | tr -d '%')
awk -v t="$total" 'BEGIN { if (t+0 < 95.0) { print "FAIL: " t "% < 95%"; exit 1 } }'
```

### Frontend: vitest.config.ts thresholds

After adding `coverage.thresholds`, running `pnpm test:coverage` exits non-zero if any metric is below 95% for the shared frontend runtime modules covered by `vitest.config.ts`.

---

## Branch Protection Rules (Manual Configuration)

After `ci.yml` is merged to `main`, configure these GitHub branch protection rules for `main`:

1. **Require status checks to pass before merging**: Enable
   - Required checks: `Lint Python`, `Type-check Python`, `Test Python`, `Lint Go`, `Test Go`, `Lint Frontend`, `Test Frontend`, `Build image`, `Helm lint`, `Migration chain integrity`, `Proto lint`, `Secret scan`
2. **Require branches to be up to date before merging**: Enable
3. **Require pull request reviews before merging**: At least 1 approver
4. **Restrict who can push to matching branches**: Configure per team policy
5. **Do not allow bypassing the above settings**: Enable

---

## Notes

- The `db-check.yml` workflow should be deleted once `ci.yml` is merged and confirmed working on `main`. Its PostgreSQL, Helm lint, and migration check jobs are fully absorbed.
- GitHub Container Registry (`ghcr.io`) is zero-config for GitHub Actions — `GITHUB_TOKEN` has write access to packages automatically.
- The first run of Trivy may take longer (scanning base images). Subsequent runs are faster due to layer caching.
- `buf.build/grpc/go` remote plugin requires internet access from the CI runner — it downloads from the Buf Schema Registry.
