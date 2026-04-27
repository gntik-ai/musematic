# UPD-043 Repository Inventory

Date: 2026-04-27
Branch: `093-workspace-owner-workbench`

## Upstream Wave Status

- UPD-040 is merged to `main`: `e5374bb Merge pull request #90 from gntik-ai/090-hashicorp-vault-integration`.
- UPD-041 is merged to `main`: `2cf5cdb Merge pull request #91 from gntik-ai/091-oauth-env-bootstrap`.
- UPD-042 is merged to `main`: `193d82f Merge pull request #92 from gntik-ai/092-user-notification-self-service`.
- Implementation is not blocked by the UPD-040/041/042 merge gate.

## Required File Inventory

- `apps/control-plane/src/platform/workspaces/router.py`: present. Lines 50-346 expose the expected 18 workspace endpoints: CRUD, members, settings, visibility, goals, and governance-chain.
- `apps/control-plane/src/platform/connectors/router.py`: present. Lines 82-237 expose the expected 14 workspace-scoped connector endpoints for CRUD, health-check, routes, deliveries, and dead-letter flows.
- `apps/control-plane/src/platform/connectors/models.py`: `ConnectorInstance.workspace_id` is `nullable=False` at lines 89-92.
- `apps/web/components/features/admin/AdminSettingsPanel.tsx`: present. Lines 16-39 define the 7-tab array: `users`, `signup`, `quotas`, `connectors`, `email`, `oauth`, and `security`.
- `apps/web/app/(main)/workspaces/[id]/*`: absent. No workspace-owner UI route tree exists today.
- `apps/web/package.json`: contains `@xyflow/react` and `@dagrejs/dagre`. No Cytoscape dependency is present.
- `apps/control-plane/migrations/versions/070_user_self_service_extensions.py`: present. The next migration slot for UPD-043 is `071`.

## 2PA Inventory Note

The task text says no existing 2PA implementation exists. Source-level service/router implementation is absent, but the database schema is not fully greenfield: `apps/control-plane/migrations/versions/067_admin_workbench.py` already creates `two_person_auth_requests`.

UPD-043 should avoid duplicating 2PA concepts blindly. The implementation should either reuse/extend that existing table or document a deliberate schema replacement before adding `two_person_approval_challenges`.
