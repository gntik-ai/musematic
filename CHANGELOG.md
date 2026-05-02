# Changelog

## Unreleased

- Added UPD-048 Public Signup at Default Tenant Only: default-tenant public signup with workspace/subscription auto-provisioning, opaque 404s on Enterprise signup surfaces, first-admin `/setup` with mandatory MFA, cross-tenant identity handling, onboarding, memberships, and tenant switcher support.
- Added UPD-047 Plans, Subscriptions, and Quotas: billing plan versioning, subscription lifecycle management, quota enforcement, overage authorization, metering, admin subscription operations, and billing observability/runbook coverage.
- Clarified the repository test taxonomy after the historical `apps/control-plane/tests/e2e` rename: control-plane docker-compose and in-process suites live under `apps/control-plane/tests/integration`, while the kind-based harness for feature 071 lives at repository-root `tests/e2e`.
