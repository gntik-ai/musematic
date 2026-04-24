# Integrations and Credentials

## SDK publishing secrets

The `sdks.yml` workflow requires four credentials in the repository Actions secrets store.

| Secret | Provisioning | Purpose |
|---|---|---|
| `PYPI_TOKEN` | Operator-provisioned one time | Publishes the Python SDK package to PyPI |
| `NPM_TOKEN` | Operator-provisioned one time | Publishes the TypeScript SDK package to npm |
| `CRATES_IO_TOKEN` | Operator-provisioned one time | Publishes the Rust SDK crate to crates.io |
| `GITHUB_TOKEN` | Auto-provisioned by GitHub Actions | Uploads the Go SDK artifact and `openapi.json` to the GitHub release |

## Operational notes

- Store the three external registry tokens only in the repository or organisation Actions secrets store.
- Rotate `PYPI_TOKEN`, `NPM_TOKEN`, and `CRATES_IO_TOKEN` in their respective registries and update GitHub Actions secrets immediately after rotation.
- `GITHUB_TOKEN` is managed by GitHub Actions and does not need manual provisioning.
- The SDK workflow can be re-run manually with `workflow_dispatch`; set `dry_run=true` to regenerate artifacts without publishing them.
- Cross-reference the shipped feature summary in `docs/features/073-api-governance-dx.md` when reviewing release-time API governance changes.
