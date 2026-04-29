# Tag and Label Rules

Tags and labels are shared organizational metadata attached through the common tagging substrate, not per-entity columns.

## Tags

Tags are case-sensitive strings. The service trims surrounding whitespace and then enforces:

```text
^[a-zA-Z0-9._-]+$
```

Limits:

| Limit | Value |
| --- | --- |
| Maximum tags per entity | 50 |
| Maximum tag length | 128 characters |

Re-applying the same tag to the same `(entity_type, entity_id)` is idempotent.

## Labels

Labels are string key-value pairs. Keys are unique per entity, so writing an existing key updates its value in place and records the old value in the audit chain.

Key rule:

```text
^[a-zA-Z][a-zA-Z0-9._-]*$
```

Limits:

| Limit | Value |
| --- | --- |
| Maximum labels per entity | 50 |
| Maximum label key length | 128 characters |
| Maximum label value length | 512 characters |

## Reserved Namespaces

The prefixes `system.` and `platform.` are reserved for platform-managed labels. Non-superadmin users cannot write them. Superadmins and service-account callers can write reserved labels through the service boundary and the segregated admin REST endpoint:

```text
/api/v1/admin/labels/reserved/*
```

Reserved labels are still visible with the parent entity to users who can view that entity.
