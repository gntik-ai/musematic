# Two-Person Approval Primitive

The two-person approval primitive stores a frozen server-side action payload and allows a distinct co-signer to approve it before the initiator consumes it.

## Contract

- `create_challenge(initiator_id, action_type, action_payload, ttl_seconds)` persists the action payload exactly once.
- `approve_challenge(challenge_id, co_signer_id)` rejects `co_signer_id == initiator_id`.
- `consume_challenge(challenge_id, requester_id)` requires the requester to be the initiator and executes the frozen payload, not a client-resubmitted payload.
- State transitions are one-way: `pending -> approved -> consumed`; expired and consumed challenges cannot be reused.

## Registering Actions

Add a new action type only for server-owned destructive or high-risk operations. The handler should accept the frozen payload, revalidate authorization at consume time, perform the operation atomically, and emit audit events.

Workspace ownership transfer is the first action type: `workspace_transfer_ownership`.

## Invariants

Future handlers must preserve same-actor refusal, short TTL, atomic transition locking, and TOCTOU prevention. The challenge response should expose metadata only; raw action payloads stay server-side until consume dispatch.
