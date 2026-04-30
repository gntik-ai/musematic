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

## 2026-04-30 Session Note

The live audit-row count check could not be completed in this sandbox session because the platform API was not running at `http://localhost:8081` and no kind cluster was available. The local backend verification still passed (`37 passed` for the UPD-043 backend slice), but T094 remains pending until a running platform database can be exercised and `audit_chain_entries` row deltas can be asserted.
