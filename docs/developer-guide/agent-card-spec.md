# Agent Card Spec

Agent cards make agents discoverable and reviewable. A card should include FQN, display name, owner, purpose, approach, supported inputs, supported outputs, trust status, package revision, model binding, tool requirements, visibility, and support contact.

Required fields:

| Field | Purpose |
| --- | --- |
| `fqn` | Stable fully qualified name. |
| `purpose` | Narrow statement of allowed work. |
| `approach` | How the agent uses context, tools, and models. |
| `owner` | Team or user accountable for maintenance. |
| `revision` | Package or metadata revision. |
| `default_model_binding` | Catalog model binding validated before runtime. |
| `visibility` | Workspace or marketplace exposure. |

Cards should avoid secrets, private prompts, and unsupported claims.
