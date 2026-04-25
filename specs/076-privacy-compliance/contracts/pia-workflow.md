# PIA Workflow Contract

**Feature**: 076-privacy-compliance
**Module**: `apps/control-plane/src/platform/privacy_compliance/services/pia_service.py`

## Lifecycle

```
draft ──[submit for review]──▶ under_review
under_review ──[approve]──────▶ approved
under_review ──[reject]───────▶ rejected
approved ──[material change detected]──▶ superseded (terminal)
```

## Data categories requiring PIA

`DATA_CATEGORIES_REQUIRING_PIA = {"pii", "phi", "financial", "confidential"}`.

An agent with any matching declared `data_categories` cannot complete
certification without an `approved` PIA (FR-023).

## Service API

```python
class PIAService:
    async def submit_draft(
        self,
        *,
        subject_type: str,
        subject_id: UUID,
        data_categories: list[str],
        legal_basis: str,
        retention_policy: str | None,
        risks: list[dict],
        mitigations: list[dict],
        submitted_by: UUID,
    ) -> PIA: ...

    async def submit_for_review(self, pia_id: UUID, actor: UUID) -> PIA: ...

    async def approve(self, pia_id: UUID, approver: UUID) -> PIA:
        """Rule 33: approver != submitter."""

    async def reject(self, pia_id: UUID, reviewer: UUID, feedback: str) -> PIA: ...

    async def check_material_change(
        self,
        subject_type: str,
        subject_id: UUID,
        new_data_categories: list[str],
    ) -> list[PIA]:
        """Called by registry on agent update; supersedes affected PIAs
        when declared categories materially change."""

    async def get_approved_pia(
        self,
        subject_type: str,
        subject_id: UUID,
    ) -> PIA | None:
        """For certification gating."""
```

## Certification integration

Hook in `trust/services/certification_service.py`:

```python
async def request_certification(self, agent_id: UUID):
    agent = await agents_repo.get(agent_id)
    if any(c in DATA_CATEGORIES_REQUIRING_PIA for c in agent.declared_data_categories):
        pia = await pia_service.get_approved_pia("agent", agent_id)
        if pia is None:
            raise CertificationBlocked(
                reason="pia_required",
                detail=f"Agent {agent_id} declares data categories {agent.declared_data_categories}; an approved PIA is required before certification.",
            )
    # proceed with existing logic (feature 075's model-card check also lives here)
    ...
```

## Material-change detection

Called from registry when an agent's manifest is updated:

```python
# registry/service.py — on agent update
material_change = set(new_categories) != set(old_categories)
if material_change and any(c in DATA_CATEGORIES_REQUIRING_PIA for c in new_categories):
    superseded = await pia_service.check_material_change(
        "agent", agent_id, new_categories
    )
    # superseded PIAs emit `privacy.pia.superseded` event
```

## REST endpoints

Under `/api/v1/privacy/pia/*`:

| Method + path | Purpose | Role |
|---|---|---|
| `POST /api/v1/privacy/pia` | Submit draft | any authenticated user with workspace-admin role for the subject |
| `GET /api/v1/privacy/pia` | List (filter by subject, status) | `privacy_officer`, `auditor`, `compliance_officer`, `superadmin` |
| `GET /api/v1/privacy/pia/{id}` | Get single PIA | same |
| `POST /api/v1/privacy/pia/{id}/submit` | Draft → under_review | submitter |
| `POST /api/v1/privacy/pia/{id}/approve` | Approve (2PA) | `privacy_officer`, `superadmin` (not the submitter) |
| `POST /api/v1/privacy/pia/{id}/reject` | Reject with feedback | `privacy_officer`, `superadmin` |
| `GET /api/v1/privacy/pia/subject/{subject_type}/{subject_id}/active` | Get approved PIA for subject | public to workspace members (read-only) |

## Audit chain + Kafka events

Every state transition writes an audit chain entry and emits a Kafka
event:
- `privacy.pia.drafted`
- `privacy.pia.submitted_for_review`
- `privacy.pia.approved`
- `privacy.pia.rejected`
- `privacy.pia.superseded`

## Unit-test contract

- **PIA1** — submit draft with all fields → row created with `status='draft'`.
- **PIA2** — submit with missing `legal_basis` → rejected.
- **PIA3** — approve by submitter → 403 (rule 33).
- **PIA4** — approve by privacy_officer → `status='approved'`,
  `approved_by`/`approved_at` set.
- **PIA5** — reject with feedback → `status='rejected'`, feedback
  stored.
- **PIA6** — certification blocked without PIA when declared
  categories include `pii`.
- **PIA7** — certification proceeds with approved PIA.
- **PIA8** — material category change supersedes prior PIA;
  `status='superseded'`; Kafka event emitted.
