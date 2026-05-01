# Creator Context Profile Format

Context profiles are JSON documents validated by the backend Pydantic schema
served at `/api/v1/context-engineering/profiles/schema`.

## Key Fields

- `name`: workspace-unique profile name.
- `source_config`: retrieval sources, priorities, strategies, provenance flags,
  and data classification.
- `budget_config`: token and source limits.
- `compaction_strategies`: ordered compaction strategy names.
- `quality_weights`: scoring weights used by context quality logic.
- `privacy_overrides`: profile-specific privacy behavior.

## Provenance

Preview responses include source origin, snippet, score, inclusion flag,
classification, and optional exclusion reason. The same provenance shape powers
the profile Test tab and the execution drilldown Context tab.

## Versioning

Every create/update stores a JSONB snapshot in
`context_engineering_profile_versions`. Diffs are computed from snapshots.
Rollback creates a new version from the selected snapshot and does not mutate
the historical row.
