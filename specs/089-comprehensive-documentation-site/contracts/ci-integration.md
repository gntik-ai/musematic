# CI Integration Contract for UPD-039

Verified on 2026-04-27 against `.github/workflows/ci.yml`.

## Existing Path Filters

The `changes` job uses `dorny/paths-filter@v3` and currently defines these filters:

- `python`
- `go-reasoning`
- `go-runtime`
- `go-sandbox`
- `go-simulation`
- `frontend`
- `helm`
- `migrations`
- `proto`
- `images`
- `readme`

There is no `docs` filter before UPD-039.

## Docs Filter Insertion Point

UPD-039 appends a `docs` filter after the `readme` filter:

```yaml
docs:
  - 'docs/**'
  - 'mkdocs.yml'
  - 'requirements-docs.txt'
  - 'scripts/generate-env-docs.py'
  - 'scripts/check-doc-references.py'
  - 'scripts/export-openapi.py'
  - 'scripts/aggregate-helm-docs.py'
```

The `changes` job exports `docs: ${{ steps.filter.outputs.docs }}` so downstream
jobs can key off it.

## Docs Staleness Job

The `docs-staleness` job slots after `readme-parity` and before language-specific
build/test jobs. It is conditional on docs or Helm changes:

```yaml
if: needs.changes.outputs.docs == 'true' || needs.changes.outputs.helm == 'true'
```

The job installs Python 3.12, docs requirements, and `helm-docs` before running:

1. Env-var drift check:
   `python scripts/generate-env-docs.py > /tmp/env-vars.md` and diff against
   `docs/configuration/environment-variables.md`.
2. Helm-values drift check:
   `python scripts/aggregate-helm-docs.py > /tmp/helm-values.md` and diff against
   `docs/configuration/helm-values.md`.
3. FR-reference drift check:
   `python scripts/check-doc-references.py docs/`.

Failures are captured in `/tmp/docs-staleness.out` and posted to pull requests with
remediation instructions.

## Separate Docs Build Workflow

`.github/workflows/docs-build.yml` owns the strict MkDocs build and GitHub Pages
deployment through `mike`. It runs on pull requests touching documentation-related
paths and on push to `main`.
