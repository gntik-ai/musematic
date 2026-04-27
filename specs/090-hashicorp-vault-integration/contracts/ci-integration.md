# CI Integration — UPD-040

Date: 2026-04-27

## Existing CI Substrate

- `.github/workflows/ci.yml` uses `dorny/paths-filter@v3` in the `changes` job.
- The current filter includes `python`, per-service Go filters, `frontend`, `helm`, `migrations`, `proto`, `images`, `readme`, `docs`, and `terraform`.
- UPD-039 documentation support is present in CI:
  - `docs:` path filter exists.
  - `scripts/generate-env-docs.py`, `scripts/check-doc-references.py`, `scripts/check-doc-translation-parity.py`, `scripts/export-openapi.py`, and `scripts/aggregate-helm-docs.py` are included in the docs filter.
  - The docs staleness job regenerates environment variable docs and checks documentation references/parity.

## UPD-040 Additions

- Add a `check-secret-access` job that runs `python scripts/check-secret-access.py` on every PR path set that can affect secret resolution (`python`, any Go service, `helm`, or the script itself).
- The job should fail on exit code `1` for direct secret-pattern environment access and on exit code `2` for parse errors.
- Extend the path filter to include `scripts/check-secret-access.py` under the relevant Python/docs-script checks.

## Later Matrix CI Plan

- Add a `journey-tests` matrix job in T108.
- Matrix axis: `secret_mode: [mock, kubernetes, vault]`.
- Each matrix entry sets `PLATFORM_VAULT_MODE` and runs the existing J01 Administrator and J11 Security Officer journey suites.
- The matrix job should reuse the existing kind bootstrap and journey reporting harness under `tests/e2e/journeys/`.
