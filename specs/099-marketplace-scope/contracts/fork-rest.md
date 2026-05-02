# Contract — Fork Operation REST API

**Endpoint**: `POST /api/v1/registry/agents/{source_id}/fork`
**Owner**: `apps/control-plane/src/platform/registry/service.py:RegistryService.fork_agent`
**Authorization**: Authenticated user with read access to the source agent (per the new `agents_visibility` RLS policy) AND write access in the target workspace/tenant.

## Request

```jsonc
{
  "target_scope": "tenant",                       // "workspace" | "tenant" — never "public_default_tenant"
  "target_workspace_id": "uuid",                  // required when target_scope == "workspace"
  "new_name": "acme-pdf-extractor"                // required; the consumer chooses a fresh local_name within the target namespace
}
```

## Response 201

```jsonc
{
  "agent_id": "uuid",
  "fqn": "acme-tools:acme-pdf-extractor",
  "marketplace_scope": "tenant",
  "review_status": "draft",
  "forked_from_agent_id": "uuid",
  "forked_from_fqn": "musematic-tools:pdf-extractor",
  "tool_dependencies_missing": []
}
```

## Behaviour

1. Verifies the source is visible to the consumer (RLS handles this — if the source is not visible, the read returns no rows and the fork is refused with 404).
2. Verifies the consumer can write to the target scope (existing workspace/tenant RBAC).
3. Verifies the consumer's `max_agents_per_workspace` quota (UPD-047) — refused with 402 if at cap.
4. Deep-copies the source agent's configuration: prompts, capability declarations, tool dependencies, behaviour metadata. NOT copied: review status (resets to `draft`), reviewer attribution, marketing metadata (forks are private), the source's tenant_id (replaced with consumer's).
5. Sets `forked_from_agent_id = source_id`. The source agent is unchanged.
6. Surfaces tool dependencies that are not registered in the consumer's tenant; the response includes a `tool_dependencies_missing` array (warnings, not errors — the fork still succeeds, but execution will fail until those tools are registered).
7. Records audit-chain entry. Publishes `marketplace.forked` Kafka event.

## Error model

| HTTP | `code` |
|---|---|
| 401 | `unauthenticated` |
| 402 | `quota_exceeded` (max_agents_per_workspace) |
| 403 | `not_authorized_in_target_workspace`, `consume_public_marketplace_disabled` |
| 404 | `source_agent_not_visible` |
| 422 | `target_workspace_required`, `new_name_invalid`, `target_scope_invalid` |
| 409 | `name_taken_in_target_namespace` |

## Source-update notification

When the source agent is later updated and re-approved, every fork's owner receives a notification via `AlertService.create_admin_alert()` with type `marketplace.source_updated`. The notification carries:

- The source agent's FQN.
- A summary of changes (new version + diff hash; no automatic detail rendering — the owner clicks through to the source detail page if interested).
- A clear statement that the fork has NOT been auto-updated.

## Test contract

`tests/integration/marketplace/test_fork_*.py`:

- `test_fork_into_tenant.py` — happy path, deep copy verified.
- `test_fork_into_workspace.py` — happy path with workspace target.
- `test_fork_quota_refusal.py` — refused at cap.
- `test_fork_tool_dependency_warning.py` — fork succeeds; warning surfaced.
- `test_source_update_notifies_forks.py` — source update produces notifications to all forks.
