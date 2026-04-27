# Planning Input — Tags, Labels, and Saved Views

> Verbatim brownfield input that motivated this spec. Preserved here as a
> planning artifact. The implementation strategy (specific tables,
> services, schemas, code-level integration points) is intentionally
> deferred to the planning phase. This file is a planning input, not a
> contract.

## Brownfield Context
**Modifies:** All major entity tables (`workspaces`, `agents`, `fleets`, `workflows`, `policies`, `certifications`, `evaluation_suites`)
**FRs:** FR-511, FR-512

## Summary
Add tags (free-form) and labels (key-value) to all major entities. Enable label-based policy expressions. Add saved views (named filter combinations) per user with sharing per workspace.

## Database Changes (planning input — not a contract)
```sql
-- Polymorphic tag/label system
CREATE TABLE entity_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(32) NOT NULL,
    entity_id UUID NOT NULL,
    tag VARCHAR(128) NOT NULL,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_type, entity_id, tag)
);
CREATE INDEX idx_entity_tags_type_id ON entity_tags(entity_type, entity_id);
CREATE INDEX idx_entity_tags_tag ON entity_tags(tag);

CREATE TABLE entity_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(32) NOT NULL,
    entity_id UUID NOT NULL,
    label_key VARCHAR(128) NOT NULL,
    label_value VARCHAR(512) NOT NULL,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_type, entity_id, label_key)
);
CREATE INDEX idx_entity_labels_type_id ON entity_labels(entity_type, entity_id);
CREATE INDEX idx_entity_labels_kv ON entity_labels(label_key, label_value);

CREATE TABLE saved_views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES users(id),
    workspace_id UUID REFERENCES workspaces(id),
    name VARCHAR(256) NOT NULL,
    entity_type VARCHAR(32) NOT NULL,
    filters JSONB NOT NULL,
    shared BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## New Files
- `common/tagging/tag_service.py` — generic tag CRUD per entity type
- `common/tagging/label_service.py` — generic label CRUD
- `common/tagging/saved_view_service.py`
- `common/tagging/router.py` — generic endpoints `/api/v1/{entity_type}/{id}/tags` and `/labels`
- `common/tagging/policy_expressions.py` — label-based expressions (e.g., `env=production AND tier=critical`)

## Modified Files
- `policies/services/policy_engine.py` — evaluate label-based expressions in policy rules
- `registry/services/registry_query_service.py` — support `?tags=x,y&label.env=production` filters

## Acceptance Criteria
- [ ] Tags addable to all major entity types
- [ ] Labels addable with key-value semantics
- [ ] Tag search across entity types
- [ ] Label-based policy expressions evaluable
- [ ] Saved views per user with workspace sharing
