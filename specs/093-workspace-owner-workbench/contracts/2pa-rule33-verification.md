# Rule 33 Two-Person Approval Verification

Status: targeted unit coverage added; live concurrency stress pending.

## Invariants

- Same-actor approval is rejected.
- Expired challenges cannot be approved or consumed.
- Consumed challenges cannot be consumed twice.
- Consume dispatch uses the frozen server-side payload.
- State transitions are serialized with row locking in the service path.

## Local Coverage

`apps/control-plane/tests/two_person_approval/test_service.py` and `apps/control-plane/tests/two_person_approval/test_router.py` cover create, approve, consume, same-actor refusal, expiry, double consume, and server-side action dispatch.

## Pending

Run a live concurrent-approve stress check against PostgreSQL to prove only one co-signer wins under contention.
