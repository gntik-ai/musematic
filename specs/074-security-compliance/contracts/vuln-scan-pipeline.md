# Vulnerability Scan Pipeline Contract

**Feature**: 074-security-compliance
**Files**:
- `.github/workflows/ci.yml` (extend)
- `ci/normalize_scan_results.py`
- `apps/control-plane/src/platform/security_compliance/services/vuln_scan_service.py`

## Scanner matrix

Jobs added to `ci.yml` (parallel; all must succeed or produce
results):

| Scanner | Language / layer | Gate severity | Installer |
|---|---|---|---|
| **Trivy** (existing) | Container images | `critical` on runtime | already installed |
| **Gitleaks** (existing) | Repo secrets | any | already installed |
| **pip-audit** | Python deps in `apps/control-plane/` + `apps/ops-cli/` | `critical` | `pip install pip-audit` |
| **govulncheck** | Go modules in `services/*` | `high` | `go install golang.org/x/vuln/cmd/govulncheck@latest` |
| **bandit** | Python SAST | `high` | `pip install bandit[toml]` |
| **gosec** | Go SAST | `high` | `go install github.com/securego/gosec/v2/cmd/gosec@latest` |
| **npm audit** | JS deps in `apps/web/` | `high` | builtin |

Each job emits SARIF or JSON to `scan-results/<scanner>.json`. A
final `upload-security-artefacts` job runs `ci/normalize_scan_results.py`
which:

1. Reads each scanner's output.
2. Normalises into the shape `{scanner, release_version, findings[],
   max_severity, scanned_at, gating_result}`.
3. Consults the `vulnerability_exceptions` table (via admin API) for
   active exceptions per finding.
4. Determines `gating_result = 'blocked' if any non-excepted finding
   at gate severity else 'passed'`.
5. POSTs to `/api/v1/security/scans/{release_version}/results` for
   each scanner.
6. If any `gating_result == 'blocked'`, exits non-zero (fails the CI
   job → blocks the release).

## Dev-only exception

A `scan-metadata.json` manifest at repo root declares which
components are dev-only; the normaliser downgrades findings against
those components to non-blocking (integration-constraint 9.2).

## REST endpoints

| Method + path | Purpose | Role |
|---|---|---|
| `POST /api/v1/security/scans/{release_version}/results` | Ingest one scan | `release_publisher` |
| `GET /api/v1/security/scans/{release_version}` | List all scans for release | `auditor`, `superadmin` |
| `GET /api/v1/security/scans/{release_version}/status` | Aggregate gating result | `auditor`, `superadmin` |
| `POST /api/v1/security/vulnerability-exceptions` | Create exception | `superadmin` (2PA required) |
| `GET /api/v1/security/vulnerability-exceptions` | List active exceptions | `auditor`, `superadmin` |

## Test IDs

- **VS1** — blocked release: inject stub critical CVE → normaliser
  exits non-zero.
- **VS2** — exception path: add exception → blocked becomes passed.
- **VS3** — dev-dep: same CVE in dev dep → not blocked.
- **VS4** — aggregate status: one scanner blocked → aggregate blocked.
- **VS5** — 2PA on exception create: requester cannot self-approve.
