# Interface Contracts: CI/CD Workflow Schemas

**Feature**: [spec.md](../spec.md)  
**Contract type**: GitHub Actions workflow YAML structure

---

## ci.yml — Continuous Integration Workflow

**File**: `.github/workflows/ci.yml`  
**Triggers**: `pull_request` (all branches), `push` (branch: `main`)

### Annotated Schema

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  packages: read
  security-events: write   # Required for Trivy SARIF upload

jobs:

  # ── PATH DETECTION ────────────────────────────────────────────────────────
  changes:
    name: Detect changed paths
    runs-on: ubuntu-latest
    outputs:
      python: ${{ steps.filter.outputs.python }}
      go-reasoning: ${{ steps.filter.outputs.go-reasoning }}
      go-runtime: ${{ steps.filter.outputs.go-runtime }}
      go-sandbox: ${{ steps.filter.outputs.go-sandbox }}
      go-simulation: ${{ steps.filter.outputs.go-simulation }}
      frontend: ${{ steps.filter.outputs.frontend }}
      helm: ${{ steps.filter.outputs.helm }}
      migrations: ${{ steps.filter.outputs.migrations }}
      proto: ${{ steps.filter.outputs.proto }}
      images: ${{ steps.filter.outputs.images }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            python:
              - 'apps/control-plane/**'
            go-reasoning:
              - 'services/reasoning-engine/**'
            go-runtime:
              - 'services/runtime-controller/**'
            go-sandbox:
              - 'services/sandbox-manager/**'
            go-simulation:
              - 'services/simulation-controller/**'
            frontend:
              - 'apps/web/**'
            helm:
              - 'deploy/helm/**'
            migrations:
              - 'apps/control-plane/migrations/**'
            proto:
              - 'services/*/proto/**'
            images:
              - 'apps/control-plane/**'
              - 'apps/web/**'
              - 'services/**'

  # ── PYTHON QUALITY GATES ─────────────────────────────────────────────────
  lint-python:
    name: Lint Python
    needs: changes
    if: needs.changes.outputs.python == 'true'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/control-plane
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff check .

  typecheck-python:
    name: Type-check Python
    needs: changes
    if: needs.changes.outputs.python == 'true'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/control-plane
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: mypy src/platform

  test-python:
    name: Test Python (≥95% coverage)
    needs: changes
    if: needs.changes.outputs.python == 'true'
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: musematic
          POSTGRES_PASSWORD: postgres
          POSTGRES_USER: postgres
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 5
    defaults:
      run:
        working-directory: apps/control-plane
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: pytest --cov=platform --cov-report=xml --cov-fail-under=95
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/musematic
          REDIS_TEST_MODE: standalone
          REDIS_URL: redis://localhost:6379
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: python-coverage
          path: apps/control-plane/coverage.xml

  # ── GO QUALITY GATES ─────────────────────────────────────────────────────
  lint-go:
    name: Lint Go (${{ matrix.service }})
    needs: changes
    if: |
      needs.changes.outputs.go-reasoning == 'true' ||
      needs.changes.outputs.go-runtime == 'true' ||
      needs.changes.outputs.go-sandbox == 'true' ||
      needs.changes.outputs.go-simulation == 'true'
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - service: reasoning-engine
            filter: go-reasoning
          - service: runtime-controller
            filter: go-runtime
          - service: sandbox-manager
            filter: go-sandbox
          - service: simulation-controller
            filter: go-simulation
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version-file: services/${{ matrix.service }}/go.mod
          cache: true
      - uses: golangci/golangci-lint-action@v6
        with:
          version: latest
          working-directory: services/${{ matrix.service }}

  test-go:
    name: Test Go (${{ matrix.service }}, ≥95% coverage)
    needs: changes
    if: |
      needs.changes.outputs.go-reasoning == 'true' ||
      needs.changes.outputs.go-runtime == 'true' ||
      needs.changes.outputs.go-sandbox == 'true' ||
      needs.changes.outputs.go-simulation == 'true'
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - service: reasoning-engine
            filter: go-reasoning
          - service: runtime-controller
            filter: go-runtime
          - service: sandbox-manager
            filter: go-sandbox
          - service: simulation-controller
            filter: go-simulation
    defaults:
      run:
        working-directory: services/${{ matrix.service }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version-file: services/${{ matrix.service }}/go.mod
          cache: true
      - run: go test -race -coverprofile=coverage.out ./...
      - name: Check coverage threshold
        run: |
          total=$(go tool cover -func=coverage.out | grep "^total:" | awk '{print $3}' | tr -d '%')
          echo "Coverage: ${total}%"
          awk -v t="$total" 'BEGIN { if (t+0 < 95.0) { print "FAIL: coverage " t "% < 95%"; exit 1 } }'
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: go-coverage-${{ matrix.service }}
          path: services/${{ matrix.service }}/coverage.out

  # ── FRONTEND QUALITY GATES ───────────────────────────────────────────────
  lint-frontend:
    name: Lint Frontend
    needs: changes
    if: needs.changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: pnpm
          cache-dependency-path: apps/web/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm type-check

  test-frontend:
    name: Test Frontend (≥95% coverage)
    needs: changes
    if: needs.changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: pnpm
          cache-dependency-path: apps/web/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
      - run: pnpm test:coverage
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: frontend-coverage
          path: apps/web/coverage/

  # ── IMAGE BUILDS ─────────────────────────────────────────────────────────
  build-images:
    name: Build image (${{ matrix.image }})
    needs: changes
    if: needs.changes.outputs.images == 'true'
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - image: control-plane
            dockerfile: apps/control-plane/Dockerfile
            context: apps/control-plane
          - image: web
            dockerfile: apps/web/Dockerfile
            context: apps/web
          - image: reasoning-engine
            dockerfile: services/reasoning-engine/Dockerfile
            context: services/reasoning-engine
          - image: runtime-controller
            dockerfile: services/runtime-controller/Dockerfile
            context: services/runtime-controller
          - image: sandbox-manager
            dockerfile: services/sandbox-manager/Dockerfile
            context: services/sandbox-manager
          - image: simulation-controller
            dockerfile: services/simulation-controller/Dockerfile
            context: services/simulation-controller
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/${{ github.repository }}/${{ matrix.image }}
          tags: |
            type=sha,prefix=sha-
      - uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.dockerfile }}
          push: false
          load: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ── INFRASTRUCTURE CHECKS ────────────────────────────────────────────────
  helm-lint:
    name: Helm lint + validate
    needs: changes
    if: needs.changes.outputs.helm == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/setup-helm@v4
      - name: Install kubeconform
        run: |
          curl -sSL -o kc.tar.gz https://github.com/yannh/kubeconform/releases/download/v0.6.7/kubeconform-linux-amd64.tar.gz
          tar -xzf kc.tar.gz kubeconform
          sudo mv kubeconform /usr/local/bin/
      - name: Lint and validate all charts
        run: |
          for chart in deploy/helm/*/; do
            echo "=== $chart ==="
            helm dependency build "$chart" 2>/dev/null || true
            helm lint "$chart" --strict
            helm template release "$chart" | \
              kubeconform -strict -ignore-missing-schemas -kubernetes-version 1.29.0
          done

  migration-check:
    name: Migration chain integrity
    needs: changes
    if: needs.changes.outputs.migrations == 'true'
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: musematic
          POSTGRES_PASSWORD: postgres
          POSTGRES_USER: postgres
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    defaults:
      run:
        working-directory: apps/control-plane
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -e ".[dev]"
      - name: Apply migrations
        run: make migrate
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/musematic
      - name: Verify linear chain
        run: |
          output="$(make migrate-check)"
          echo "$output"
          if echo "$output" | grep -q "Rev:"; then
            echo "Migration graph is not linear — branch or gap detected"
            exit 1
          fi
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/musematic

  proto-check:
    name: Proto lint + generate
    needs: changes
    if: needs.changes.outputs.proto == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: bufbuild/buf-action@v1
        with:
          input: services/reasoning-engine/proto
          lint: true
          format: true
          generate: true

  # ── SECURITY SCANS ───────────────────────────────────────────────────────
  security-secrets:
    name: Secret scan (gitleaks)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  security-trivy:
    name: Vulnerability scan (trivy)
    needs: build-images
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    strategy:
      fail-fast: false
      matrix:
        image: [control-plane, web, reasoning-engine, runtime-controller,
                sandbox-manager, simulation-controller]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Rebuild image for scanning
        uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.image == 'control-plane' && 'apps/control-plane' || matrix.image == 'web' && 'apps/web' || format('services/{0}', matrix.image) }}
          load: true
          tags: scan-target:${{ matrix.image }}
          cache-from: type=gha
      - uses: aquasecurity/trivy-action@master
        with:
          image-ref: scan-target:${{ matrix.image }}
          format: sarif
          output: trivy-${{ matrix.image }}.sarif
          severity: CRITICAL,HIGH
          exit-code: "0"
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: trivy-${{ matrix.image }}.sarif
          category: trivy-${{ matrix.image }}
```

---

## deploy.yml — Release Automation Workflow

**File**: `.github/workflows/deploy.yml`  
**Triggers**: `push` on tags matching `v*.*.*` (excludes `cli-v*`)

### Annotated Schema

```yaml
name: Release

on:
  push:
    tags:
      - "v*.*.*"

permissions:
  contents: write    # Create release
  packages: write    # Push to GHCR
  id-token: write    # Required for SBOM attestation (optional)

jobs:

  build-and-push:
    name: Build and push (${{ matrix.image }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - image: control-plane
            dockerfile: apps/control-plane/Dockerfile
            context: apps/control-plane
          - image: web
            dockerfile: apps/web/Dockerfile
            context: apps/web
          - image: reasoning-engine
            dockerfile: services/reasoning-engine/Dockerfile
            context: services/reasoning-engine
          - image: runtime-controller
            dockerfile: services/runtime-controller/Dockerfile
            context: services/runtime-controller
          - image: sandbox-manager
            dockerfile: services/sandbox-manager/Dockerfile
            context: services/sandbox-manager
          - image: simulation-controller
            dockerfile: services/simulation-controller/Dockerfile
            context: services/simulation-controller
    outputs:
      image-digest-${{ matrix.image }}: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/${{ github.repository }}/${{ matrix.image }}
          tags: |
            type=semver,pattern={{version}}
            type=sha,prefix=sha-
      - uses: docker/build-push-action@v6
        id: build
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.dockerfile }}
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  generate-sbom:
    name: Generate SBOM (${{ matrix.image }})
    needs: build-and-push
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        image: [control-plane, web, reasoning-engine, runtime-controller,
                sandbox-manager, simulation-controller]
    steps:
      - uses: anchore/sbom-action@v0
        with:
          image: ghcr.io/${{ github.repository }}/${{ matrix.image }}:${{ github.ref_name }}
          format: cyclonedx-json
          output-file: sbom-${{ matrix.image }}.cdx.json
      - uses: actions/upload-artifact@v4
        with:
          name: sbom-${{ matrix.image }}
          path: sbom-${{ matrix.image }}.cdx.json

  create-release:
    name: Create GitHub Release
    needs: generate-sbom
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          pattern: sbom-*
          merge-multiple: true
          path: sbom-files/
      - uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: sbom-files/*.cdx.json
          fail_on_unmatched_files: true
```

---

## vitest.config.ts — Coverage Thresholds

**File**: `apps/web/vitest.config.ts` (modification)  
Add `coverage.thresholds` to the existing config:

```typescript
// Within defineConfig({ test: { coverage: { ... } } })
thresholds: {
  lines: 95,
  branches: 95,
  functions: 95,
  statements: 95,
}
```

---

## buf.yaml — Protocol Buffer Lint Config

**File**: `services/reasoning-engine/proto/buf.yaml`

```yaml
version: v2
lint:
  use:
    - DEFAULT
    - FIELD_LOWER_SNAKE_CASE
  except: []
breaking:
  use:
    - FILE
```

## buf.gen.yaml — Code Generation Config

**File**: `services/reasoning-engine/buf.gen.yaml`

```yaml
version: v2
plugins:
  - remote: buf.build/protocolbuffers/go
    out: .
    opt: paths=source_relative
  - remote: buf.build/grpc/go
    out: .
    opt:
      - paths=source_relative
      - require_unimplemented_servers=false
```

---

## .gitleaks.toml — Secret Scanner Config

**File**: `.gitleaks.toml`

```toml
title = "Gitleaks config"

[allowlist]
description = "Global allowlisted patterns"
paths = [
  "apps/web/mocks",
  "specs",
  "docs",
]
regexes = [
  # Test fixtures with dummy credentials
  "dummy|fake|test|example|placeholder",
]
```
