# UPD-043 Cross-Feature Dependency Check

Date: 2026-04-27

## Confirmed Dependencies

- UPD-039 Comprehensive Documentation is merged to `main`: `d70b644 Merge pull request #89 from gntik-ai/089-comprehensive-documentation-site`.
- UPD-040 Vault Integration is merged to `main`: `e5374bb Merge pull request #90 from gntik-ai/090-hashicorp-vault-integration`.
- UPD-041 OAuth Bootstrap is merged to `main`: `2cf5cdb Merge pull request #91 from gntik-ai/091-oauth-env-bootstrap`.
- UPD-042 User-Facing Notification Center is merged to `main`: `193d82f Merge pull request #92 from gntik-ai/092-user-notification-self-service`.
- UPD-077 Multi-Channel Notifications is present on disk with the `platform.notifications` package and email/webhook/Slack/Teams/SMS deliverers.
- UPD-079 Cost Governance is present on disk with the `platform.cost_governance` package, router, services, ClickHouse setup, and budget service.
- UPD-033 Tags and Labels is present on disk with the `platform.common.tagging` package, routers, services, labels, saved views, and tag service.
- UPD-076/078 DLP and content-safety foundations are present on disk through `platform.privacy_compliance` DLP rules/events, DLP scanner, and DLP service.

## On-Disk Verification

- `apps/control-plane/src/platform/common/secret_provider.py` exists and exports the `SecretProvider` protocol.
- `apps/control-plane/src/platform/security_compliance/providers/rotatable_secret_provider.py` exists and provides `RotatableSecretProvider`.
- `apps/control-plane/src/platform/notifications/` exists with deliverers and persistent alert/service modules.
- `apps/control-plane/src/platform/cost_governance/` exists with `router.py`, `service.py`, and budget/forecast/anomaly service modules.
- `apps/control-plane/src/platform/common/tagging/` exists with router, repository, tag service, label service, and saved-view service.
- `apps/control-plane/src/platform/privacy_compliance/services/dlp_service.py` and DLP rule/event routes exist.
- Documentation directories from UPD-039 exist, including `docs/operator-guide/runbooks/`, `docs/admin-guide/`, `docs/developer-guide/`, and `docs/release-notes/`.

## Documentation Placement

Because UPD-039 has landed, UPD-043 runbooks and guides should be added under:

- `docs/operator-guide/runbooks/`
- `docs/admin-guide/`
- `docs/developer-guide/`
- `docs/release-notes/`
