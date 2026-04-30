# Audit Emission Verification

Status: locally mapped; live audit-row count check pending.

## Event Map

State-changing workspace-owner operations emit or are expected to emit:

- `auth.workspace.member_added`
- `auth.workspace.member_removed`
- `auth.workspace.role_changed`
- `auth.workspace.transfer_initiated`
- `auth.workspace.transfer_committed`
- `auth.workspace.budget_updated`
- `auth.workspace.quota_updated`
- `auth.workspace.dlp_rules_updated`
- `auth.workspace.connector_added`
- `auth.workspace.connector_removed`

## Local Coverage

Unit tests cover workspace summary invalidation, transfer initiation/commit, connector test-connectivity, and IBOR admin endpoints. A live audit-chain verification should hit each state-changing endpoint and assert row-count growth for each call.
