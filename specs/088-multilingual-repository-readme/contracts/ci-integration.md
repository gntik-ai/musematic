# CI Integration Contract for UPD-038

Inventory date: 2026-04-27

## Existing workflow substrate

`.github/workflows/ci.yml` is the existing per-PR CI workflow. It already contains:

- A top-level `permissions:` block with `contents: read`, `packages: read`, and `security-events: write`.
- A `changes` job that uses `dorny/paths-filter@v3`.
- Existing path filters for Python, Go satellites, frontend, Helm, migrations, protobuf, and image builds.

## UPD-038 additions

The README parity integration appends to the existing workflow rather than creating a separate per-PR docs workflow.

Required changes:

- Add `issues: write` and `pull-requests: write` to workflow permissions.
- Add a `readme` output from the `changes` job.
- Add a `readme` path filter:

```yaml
readme:
  - 'README*.md'
```

- Add a `readme-parity` job gated by `needs.changes.outputs.readme == 'true'`.
- Install `pandoc` in the job before running the parity checker.
- Run `python scripts/check-readme-parity.py`.
- Capture the script output for PR comments and drift issue creation.
- Treat exit code `1` as a warning and exit code `2` as a hard failure.

## GitHub permissions

The workflow must have:

- `issues: write` for drift tracking issues and 30-day backfill issues.
- `pull-requests: write` for parity warning comments.

The helper scripts use `GITHUB_TOKEN` and pass it to `gh` as `GH_TOKEN`.

## Labels

Repository labels needed by this integration:

- `readme-translation-drift`
- `readme-translation-backfill`
- `docs-translation-exempt`
- `external-link-rot`
- `docs`

`scripts/open-or-update-drift-issue.sh` creates the tracking labels idempotently when it runs with a token. `docs-translation-exempt` remains a maintainer-applied override label.

Verification on 2026-04-30 confirmed `docs-translation-exempt` exists in `gntik-ai/musematic` with colour `#d73a4a` and description `Exempts the PR from the README parity check; requires 30-day backfill follow-up issue per FR-602`.
