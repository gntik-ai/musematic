# Cross-Feature Dependencies — UPD-040

Date: 2026-04-27

## Current Repository State

- UPD-024 security compliance artifacts are present in the current repository state, including `security_compliance/providers/rotatable_secret_provider.py` and `security_compliance/services/secret_rotation_service.py`.
- UPD-035 / observability bundle artifacts are present through the Helm observability chart, Grafana dashboard documentation, and CI documentation staleness support.
- UPD-036 Administrator Workbench is planned in `specs/086-administrator-workbench-and/`; its task list is not fully complete in this working tree.
- UPD-039 documentation site artifacts are present, including `mkdocs.yml`, generated configuration references, and CI docs filters. Some verification tasks remain feature-owned by the documentation-site task list.

## Coordination Decisions

- `/admin/security/vault` frontend UI remains owned by UPD-036. UPD-040 ships the backend contracts and the `platform-cli vault status` fallback.
- UPD-040 documentation deliverables can live in this feature and merge into the UPD-039 docs site structure because the MkDocs substrate and generated-reference tooling are already present.
- The Vault admin endpoint contract file in T095 is the handoff artifact for UPD-036.
- If UPD-036 has not landed when UPD-040 merges, T097 must ensure the CLI status command is documented as the operator-facing fallback.

## 2026-04-30 Coordination Outcome

- The UPD-036 repository artifacts are present under `specs/086-administrator-workbench-and/`, but this working tree does not include a completed `/admin/security/vault` frontend route.
- UPD-040 therefore treats the UI page as deferred to UPD-036 or a follow-up workbench wave.
- The operator-facing fallback is `platform-cli vault status`, which calls `GET /api/v1/admin/vault/status` and presents the same health, auth, lease, cache, failure, and policy-denied fields intended for the UI panel.
- `specs/090-hashicorp-vault-integration/contracts/admin-vault-endpoints.md` is the backend contract UPD-036 should consume when adding the page.
