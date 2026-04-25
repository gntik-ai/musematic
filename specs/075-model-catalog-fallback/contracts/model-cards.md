# Model Card Contract

**Feature**: 075-model-catalog-fallback
**Module**: `apps/control-plane/src/platform/model_catalog/services/model_card_service.py`

## Endpoints

| Method + path | Purpose | Role |
|---|---|---|
| `PUT /api/v1/model-catalog/entries/{id}/card` | Create or replace card | `platform_admin`, `superadmin` |
| `GET /api/v1/model-catalog/entries/{id}/card` | Fetch card | authenticated |
| `GET /api/v1/model-catalog/entries/{id}/card/history` | List revisions | `auditor`, `platform_admin`, `superadmin` |

## Material-change detection

On `PUT /card`:

```python
async def upsert_card(entry_id: UUID, fields: ModelCardFields) -> ModelCard:
    existing = await repo.get_card(entry_id)
    new_revision = (existing.revision + 1) if existing else 1
    material = _detect_material_change(existing, fields)
    card = await repo.upsert(entry_id, fields, new_revision)
    await events.publish_model_card_published(
        entry_id=entry_id,
        card_id=card.id,
        revision=new_revision,
        material=material,
    )
    if material:
        await trust_service.flag_affected_certifications_for_rereview(
            catalog_entry_id=entry_id
        )
    return card

def _detect_material_change(old: ModelCard | None, new: ModelCardFields) -> bool:
    if old is None:
        return False  # First-time attach is not "change"
    if old.safety_evaluations != new.safety_evaluations:
        return True
    if old.bias_assessments != new.bias_assessments:
        return True
    return False
```

## Card missing → certification blocked

Trust certification service integration (extends
`trust/services/certification_service.py`):

```python
async def request_certification(self, agent_id: UUID):
    agent = await agents_repo.get(agent_id)
    binding = agent.default_model_binding
    entry = await catalog_service.get_by_binding(binding)
    if entry is None:
        raise CertificationBlocked(
            reason="model_not_in_catalogue",
            detail=f"Model {binding} not in approved catalogue",
        )
    card = await model_card_service.get_card(entry.id)
    if card is None:
        raise CertificationBlocked(
            reason="model_card_missing",
            detail=f"Model {binding} has no card; certification not permissible (FR-007)",
        )
    # Proceed with existing certification logic ...
```

## Compliance gap on missing card

Seven days after catalogue entry approval, if no card is attached,
the auto-deprecation scanner also emits a compliance-evidence gap:

```python
# In workers/auto_deprecation_scanner.py
gaps = await db.execute(text("""
    SELECT e.id, e.provider, e.model_id
    FROM model_catalog_entries e
    LEFT JOIN model_cards c ON c.catalog_entry_id = e.id
    WHERE e.status = 'approved'
      AND e.approved_at < now() - INTERVAL '7 days'
      AND c.id IS NULL
"""))
for gap in gaps:
    await compliance_service.record_gap(
        control_id=SOC2_CC7_1_UUID,
        evidence_type="model_card_missing",
        evidence_ref=f"model_catalog_entry:{gap.id}",
    )
```

## Unit-test contract

- **MC1** — attach card: PUT creates card, revision=1, no re-review.
- **MC2** — update safety_evaluations: revision=2, material=true,
  trust service flagged.
- **MC3** — update card_url only: revision=2, material=false, no
  re-review.
- **MC4** — get history: returns ordered list of revisions.
- **MC5** — certification blocked when no card: clear error.
- **MC6** — compliance gap after 7 days: evidence row written to
  compliance_evidence table.
