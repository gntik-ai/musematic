# Constitution Confirmation — UPD-040

Date: 2026-04-27

## Confirmed Anchors

- Rule 10 is present and states that every credential goes through Vault, with no plaintext secrets in code, config, database, or logs.
- Rule 30 is present and requires every admin endpoint to declare a `require_admin` or `require_superadmin` role gate, enforced by CI static analysis.
- Rule 31 is present and forbids logging super-admin bootstrap secrets.
- Rule 37 is present and requires env vars, Helm values, and feature flags to be auto-documented with CI drift checks.

## Related Rules Found During Verification

- Rule 39 explicitly requires all secret-pattern environment access to flow through `SecretProvider` implementation files and requires a CI static-analysis check.
- Rule 40 starts the Vault token log-protection section and reinforces the no-secret-log discipline for this feature.

## Decision

No spec amendment is required. The UPD-040 plan remains aligned with the current constitution text, with T023-T026 implementing the Rule 39 check and T085-T090 implementing the Rule 30 admin endpoint check.
