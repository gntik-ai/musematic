# Rule 33 Two-Person Approval Verification

Status: complete for local/PostgreSQL verification as of 2026-04-30.

## Invariants

- Same-actor approval is rejected.
- Expired challenges cannot be approved or consumed.
- Consumed challenges cannot be consumed twice.
- Consume dispatch uses the frozen server-side payload.
- State transitions are serialized with row locking in the service path.

## Local Coverage

`apps/control-plane/tests/two_person_approval/test_service.py` and `apps/control-plane/tests/two_person_approval/test_router.py` cover create, approve, consume, same-actor refusal, expiry, double consume, and server-side action dispatch.

## PostgreSQL Concurrency Verification

Executed a fresh PostgreSQL 16 container, upgraded the database through `071_workspace_owner_workbench`, inserted one initiator plus two co-signers, and raced two `TwoPersonApprovalService.approve_challenge()` calls against the same pending challenge.

Result: one transaction returned `approved`; the other returned `TWO_PERSON_APPROVAL_NOT_PENDING` after waiting on the row lock. The persisted `two_person_approval_challenges` row remained `approved` with the first co-signer's ID.

This verifies the Rule 33 atomic-transition invariant in the concrete database path using the service's `SELECT ... FOR UPDATE` query.
