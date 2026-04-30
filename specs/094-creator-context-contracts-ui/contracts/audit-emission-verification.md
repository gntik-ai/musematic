# Audit Emission Verification

Date: 2026-05-01

## State-Changing UPD-044 Events

The implementation emits structured events for the new creator actions:

- `creator.context_profile.preview_executed`
- `creator.context_profile.rolled_back`
- `creator.contract.preview_executed`
- `creator.contract.real_llm_preview_used` when real preview is explicitly used
- `creator.contract.forked_from_template`
- `creator.contract.attached_to_revision`

## Coverage

- Profile preview and rollback event paths are in
  `apps/control-plane/src/platform/context_engineering/service.py`.
- Contract preview, real-LLM opt-in, template fork, and revision attachment event
  paths are in `apps/control-plane/src/platform/trust/contract_service.py`.
- Backend tests were added for preview, rollback/versioning, template fork, and
  attach-to-revision behavior.

## Open Verification

The current implementation uses structured logging for these creator events.
The plan requested audit-chain row growth assertions against
`audit_chain_entries`; those require the full control-plane test dependency set
and migrated database. Local pytest execution is currently blocked by missing
`grpc` during shared test bootstrap.
