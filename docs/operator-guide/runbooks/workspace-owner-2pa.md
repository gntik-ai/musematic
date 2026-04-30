# Workspace Owner Two-Person Approval

## Symptom

A workspace owner needs to perform a 2PA-gated action such as ownership transfer, but the action remains pending or cannot be consumed.

## Diagnosis

Confirm the initiating user is the current workspace owner and that a different platform admin is available as co-signer. The co-signer must not be the same actor as the initiator. Check the challenge expiry; workspace-owner challenges expire automatically after the configured short TTL.

## Remediation

1. Initiate the action from `/workspaces/{id}/members`.
2. Ask a platform admin to approve the challenge from the 2PA surface.
3. Return as the initiating owner and consume the approved challenge.
4. If the challenge expired, start a new challenge with the same intended target.

## Verification

Verify the audit chain contains both `auth.workspace.transfer_initiated` and `auth.workspace.transfer_committed`. Confirm the prior owner is retained as workspace admin and the new owner has owner permissions.

## Rollback

Unconsumed challenges expire automatically. After consumption, perform a new ownership transfer back to the previous owner through the same 2PA flow.
