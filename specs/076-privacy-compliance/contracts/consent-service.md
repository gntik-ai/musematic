# Consent Service Contract

**Feature**: 076-privacy-compliance
**Module**: `apps/control-plane/src/platform/privacy_compliance/services/consent_service.py`

## Consent types

Three consent types per user:

| Type | Purpose |
|---|---|
| `ai_interaction` | The user has been informed they are interacting with an AI and consents to continue. |
| `data_collection` | The user consents to platform-level analytics on their activity. |
| `training_use` | The user consents to their messages being used in training corpora. |

## Service API

```python
class ConsentService:
    async def get_state(
        self,
        user_id: UUID,
        workspace_id: UUID | None = None,
    ) -> dict[str, ConsentState]:
        """Returns per-consent-type current state.
        State: granted / denied / never_asked."""

    async def require_or_prompt(
        self,
        user_id: UUID,
        workspace_id: UUID,
    ) -> None:
        """Raises ConsentRequired if user has not set all three.
        Called from interactions.create_conversation."""

    async def record_consents(
        self,
        user_id: UUID,
        choices: dict[str, bool],  # {"ai_interaction": True, ...}
        workspace_id: UUID | None = None,
    ) -> list[ConsentRecord]: ...

    async def revoke(
        self,
        user_id: UUID,
        consent_type: str,
    ) -> ConsentRecord:
        """Sets revoked_at; triggers propagation worker."""

    async def history(
        self,
        user_id: UUID,
    ) -> list[ConsentRecord]:
        """Full timeline including revocations."""
```

## First-interaction enforcement

In `interactions/service.py:123`:

```python
async def create_conversation(
    self,
    user_id: UUID,
    workspace_id: UUID,
    ...
) -> Conversation:
    # NEW gate
    try:
        await self._consent.require_or_prompt(user_id, workspace_id)
    except ConsentRequired as e:
        raise HTTPException(
            status_code=428,  # "Precondition Required"
            detail={
                "error": "consent_required",
                "missing_consents": e.missing_types,
                "disclosure_text_ref": "/api/v1/me/consents/disclosure",
            },
        )
    # Existing logic proceeds unchanged
    ...
```

The UI (delivered in UPD-042) handles the 428 response by rendering
the AI disclosure + consent panel.

## Self-service REST endpoints

Under `/api/v1/me/consents/*` (per rule 46, scoped to `current_user`):

| Method + path | Purpose |
|---|---|
| `GET /api/v1/me/consents` | Get own consent state |
| `PUT /api/v1/me/consents` | Record own consent choices |
| `POST /api/v1/me/consents/{type}/revoke` | Revoke a specific consent |
| `GET /api/v1/me/consents/history` | Own history (audit-style) |
| `GET /api/v1/me/consents/disclosure` | Get current disclosure text (i18n future) |

## Admin REST endpoints

Under `/api/v1/privacy/consents/*`:

| Method + path | Purpose | Role |
|---|---|---|
| `GET /api/v1/privacy/consents?user_id=` | Query consent history for a user | `privacy_officer`, `auditor`, `compliance_officer`, `superadmin` |

## Revocation propagation

APScheduler worker `consent_propagator.py` runs every 60 s:

1. Queries `privacy_consent_records WHERE revoked_at > (now() - interval '2 minutes')`.
2. For each revoked `training_use`, ensures `user_id` is in Redis set
   `privacy:revoked_training_users`.
3. Emits `privacy.consent.revoked` Kafka event (new topic).
4. Subsequent training jobs consult the Redis set and exclude
   those users when composing training corpora.
5. For `data_collection`, the analytics worker suppresses events for
   the user.
6. In-flight training jobs that have already snapshotted their corpus
   are allowed to complete (snapshot isolation per research.md D-014).

Propagation latency budget: ≤ 5 minutes end-to-end (SC-006).

## Unit-test contract

- **CO1** — first call to `create_conversation` without consents
  raises `ConsentRequired` (HTTP 428).
- **CO2** — after recording all three consents, `create_conversation`
  proceeds.
- **CO3** — partial consents (2 of 3) still trigger `ConsentRequired`.
- **CO4** — `revoke` sets `revoked_at`; history includes the grant
  and revocation.
- **CO5** — propagator worker adds user to Redis revoked set within
  60 s of revocation.
- **CO6** — training job post-revocation excludes user (verified by
  checking the corpus does not contain the user's messages).
- **CO7** — training job with snapshot-before-revocation completes
  with pre-snapshot corpus (does NOT retroactively exclude).
- **CO8** — admin audit-query returns full history including
  timestamped grants + revocations.
- **CO9** — self-service endpoints reject cross-user access attempts
  (rule 46).
