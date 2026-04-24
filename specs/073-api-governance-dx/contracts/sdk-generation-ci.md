# SDK Generation CI Contract

**Feature**: 073-api-governance-dx
**Date**: 2026-04-23
**File**: `.github/workflows/sdks.yml`

---

## Trigger

```yaml
on:
  release:
    types: [published]
  workflow_dispatch:           # manual re-run for a specific release
    inputs:
      release_tag:
        description: "Release tag (e.g. v1.4.0)"
        required: true
```

The workflow runs ONLY on a fully-published GitHub release (not on
tag push alone) because the platform image must be built + pushed by
`deploy.yml` first — the `sdks` workflow needs a running deployment
serving the corresponding OpenAPI document.

---

## Overall shape

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  1. fetch   │ →  │  2.  gen    │ →  │ 3. publish  │
│   openapi   │    │  (matrix)   │    │  (matrix)   │
└─────────────┘    └─────────────┘    └─────────────┘
                   fails atomically
```

If any matrix job in step 2 fails, step 3 does NOT run. If any
matrix job in step 3 fails, the workflow fails loudly (registries
are not rolled back — retry triggers a manual investigation).

---

## Full workflow

```yaml
name: SDKs

on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      release_tag:
        description: "Release tag (e.g. v1.4.0)"
        required: true

permissions:
  contents: write               # attach SDK artefacts to the release
  packages: write               # ghcr for caching
  id-token: write               # trusted publishing

concurrency:
  group: sdks-${{ github.event.release.tag_name || inputs.release_tag }}
  cancel-in-progress: false

jobs:

  # 1. Fetch the platform-generated OpenAPI document from the live
  # deployment corresponding to this release.
  fetch-openapi:
    name: Fetch OpenAPI document
    runs-on: ubuntu-latest
    outputs:
      openapi_sha: ${{ steps.hash.outputs.sha }}
    steps:
      - name: Resolve release version
        id: version
        run: |
          echo "version=${{ github.event.release.tag_name || inputs.release_tag }}" >> "$GITHUB_OUTPUT"

      - name: Fetch /api/openapi.json
        run: |
          set -euo pipefail
          curl --fail --retry 3 --retry-delay 5 \
            "https://api.musematic.ai/api/openapi.json" \
            --output openapi.json
          test -s openapi.json

      - name: Verify version matches release
        run: |
          jq -e --arg v "${{ steps.version.outputs.version }}" \
            '.info.version == ($v | ltrimstr("v"))' openapi.json

      - name: Filter out admin tag
        run: |
          jq 'del(.paths[] | select(.[].tags // [] | index("admin")))' openapi.json \
            > openapi.consumer.json
          mv openapi.consumer.json openapi.json

      - name: Hash for traceability
        id: hash
        run: echo "sha=$(sha256sum openapi.json | cut -d' ' -f1)" >> "$GITHUB_OUTPUT"

      - uses: actions/upload-artifact@v4
        with:
          name: openapi
          path: openapi.json
          retention-days: 90

  # 2. Generate all four SDKs in parallel. If ANY job fails, publish is blocked.
  generate:
    name: Generate ${{ matrix.lang }}
    runs-on: ubuntu-latest
    needs: [fetch-openapi]
    strategy:
      fail-fast: true
      matrix:
        lang: [python, go, typescript, rust]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: openapi
          path: .

      - name: Python — openapi-python-client
        if: matrix.lang == 'python'
        run: |
          pip install 'openapi-python-client==0.21.*'
          openapi-python-client generate --path openapi.json
          ls -1 musematic-client/

      - name: Go — oapi-codegen
        if: matrix.lang == 'go'
        run: |
          go install github.com/deepmap/oapi-codegen/v2/cmd/oapi-codegen@v2.4.0
          mkdir -p musematic-sdk-go
          oapi-codegen -generate types,client -package musematic openapi.json \
            > musematic-sdk-go/client.go

      - name: TypeScript — openapi-typescript
        if: matrix.lang == 'typescript'
        run: |
          npm install --no-save 'openapi-typescript@7' 'openapi-fetch@0.11'
          mkdir -p musematic-sdk-ts/src
          npx openapi-typescript openapi.json -o musematic-sdk-ts/src/schema.d.ts

      - name: Rust — openapi-generator-cli
        if: matrix.lang == 'rust'
        run: |
          sudo apt-get install -y openjdk-21-jre-headless
          npm install -g '@openapitools/openapi-generator-cli@2.13'
          openapi-generator-cli generate \
            -i openapi.json \
            -g rust \
            -o musematic-sdk-rust

      - uses: actions/upload-artifact@v4
        with:
          name: sdk-${{ matrix.lang }}
          path: |
            musematic-client/
            musematic-sdk-go/
            musematic-sdk-ts/
            musematic-sdk-rust/
          if-no-files-found: error

  # 3. Publish — runs ONLY if all four generate jobs succeeded.
  # All four publishes run in parallel; if any fails, workflow fails loudly.
  publish:
    name: Publish ${{ matrix.lang }}
    runs-on: ubuntu-latest
    needs: [generate]
    if: success()
    strategy:
      fail-fast: false        # try all four; report each independently
      matrix:
        lang: [python, go, typescript, rust]
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: sdk-${{ matrix.lang }}

      - name: Python — publish to PyPI
        if: matrix.lang == 'python'
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
        run: |
          pip install build twine
          cd musematic-client
          python -m build
          twine upload dist/*

      - name: Go — attach to GitHub release
        if: matrix.lang == 'go'
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh release upload ${{ github.event.release.tag_name || inputs.release_tag }} \
            musematic-sdk-go/*.go --clobber

      - name: TypeScript — publish to npm
        if: matrix.lang == 'typescript'
        env:
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
        run: |
          cd musematic-sdk-ts
          echo "//registry.npmjs.org/:_authToken=${NPM_TOKEN}" > ~/.npmrc
          npm publish

      - name: Rust — publish to crates.io
        if: matrix.lang == 'rust'
        env:
          CARGO_REGISTRY_TOKEN: ${{ secrets.CRATES_IO_TOKEN }}
        run: |
          cd musematic-sdk-rust
          cargo publish
```

---

## Secrets required in the repo's Actions-secrets store

| Secret | Purpose |
|---|---|
| `PYPI_TOKEN` | PyPI API token scoped to the `musematic-client` project |
| `NPM_TOKEN` | npm token scoped to the `@musematic` organisation |
| `CRATES_IO_TOKEN` | crates.io API token scoped to the `musematic` crate |
| `GITHUB_TOKEN` | Auto-provisioned by Actions; used by the Go step to attach assets |

These are provisioned one-time by a platform administrator; the
documentation page
[`docs/administration/integrations-and-credentials.md`][admincfg]
calls this out.

---

## Version-skew guard

Before `publish`, an additional guard job compares the current
release's OpenAPI `paths` and schema hashes against the previous
release's `openapi.json` (stored as the prior release's SDK artefact):

```yaml
guard-schema-skew:
  name: Detect breaking schema changes
  runs-on: ubuntu-latest
  needs: [fetch-openapi]
  steps:
    - uses: actions/download-artifact@v4
      with: { name: openapi, path: current/ }
    - name: Fetch previous release's OpenAPI
      run: |
        gh release download --pattern 'openapi.json' --dir previous/ \
          "$(gh release list --limit 2 | tail -1 | awk '{print $1}')" || \
          echo "no previous release; skipping"
    - name: Diff paths and schema shapes
      run: |
        if [ -f previous/openapi.json ]; then
          python -m scripts.schema_diff previous/openapi.json current/openapi.json
          # Exits non-zero if a breaking change is detected (removed path,
          # required field added, type changed) without a corresponding
          # "BREAKING:" prefix in the release notes.
        fi
```

A small Python script at `ci/schema_diff.py` (new) implements the
comparison. If breaking changes are detected without an explicit
release-notes marker, the workflow fails loudly (FR-009 atomicity
extended to "breaking changes are explicit").

---

## Test plan

- **C1** — On a normal non-breaking release, all four SDKs generate
  and publish.
- **C2** — With `PYPI_TOKEN` revoked, `publish` fails on Python; the
  other three jobs continue (fail-fast: false), so the operator sees
  exactly which registry failed.
- **C3** — Generator version bump (e.g. openapi-python-client 0.22)
  pinned explicitly in the workflow; a PR that bumps the version
  must green on a dry-run against the previous release's OpenAPI.
- **C4** — Manual re-run via `workflow_dispatch` with a historic
  release tag regenerates the SDKs for that release without
  re-publishing (add an `--dry-run` input flag).

[admincfg]: https://github.com/gntik-ai/musematic/blob/main/docs/administration/integrations-and-credentials.md
