# Creator-Side UIs

UPD-044 adds the first v1.4.0 creator-side authoring surfaces for context
engineering and agent contracts.

## Added

- Context profile editor, test panel, and version history routes.
- Agent contract editor, preview panel, history route, and template library.
- Composition wizard steps for context profile, profile test, contract,
  contract preview, and final attachment.
- Execution drilldown Context tab backed by the reusable provenance viewer.
- Eleven backend endpoints for profile preview/versioning/schema and contract
  schema, template, preview, fork, and revision attachment.
- Greenfield `MockLLMProvider` for deterministic creator previews.
- Greenfield context profile version table and contract template table.
- `agent_contracts.attached_revision_id` for revision attachment.

## Compatibility

The feature is additive. Existing context engineering, trust, registry, and
wizard flows remain in place.
