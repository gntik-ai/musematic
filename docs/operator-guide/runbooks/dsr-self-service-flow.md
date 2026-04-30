# DSR Self-Service Flow

Use this runbook for FR-656 data subject request issues from `/settings/privacy/dsr`.

## Symptom

- A user cannot submit an access, rectification, erasure, portability, restriction, or objection request.
- An erasure request is missing typed confirmation.
- The user expects a request to appear in the admin privacy queue.
- Active executions may be affected by an erasure request.

## Diagnosis

1. Confirm the user submitted through `POST /api/v1/me/dsr`; the request body must not include `subject_user_id`.
2. Confirm the created row has `subject_user_id` equal to the authenticated user and `requested_by` equal to the same user.
3. For erasure, confirm `confirm_text` is exactly `DELETE`.
4. Check the admin DSR queue under the privacy admin path and confirm the request has `source=self_service` audit metadata.

## Remediation

1. Ask the user to resubmit with the correct right type and required confirmation fields.
2. For erasure with active executions, ensure the user has acknowledged that pending executions may fail during processing.
3. Use the existing admin DSR processing and retry paths for operational handling.
4. Do not manually change the subject user. Rule 46 requires self-service scope to come from `current_user`.

## Verification

- The request appears in `GET /api/v1/me/dsr`.
- The same request appears in the admin privacy DSR queue.
- `privacy.dsr.submitted` appears in the audit chain with `source=self_service`.
- Completed access requests produce the normal secure export artifact.
