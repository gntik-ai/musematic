# Contract Template Design

Contract templates are platform-authored or creator-authored starting points for
agent contracts.

## Storage

Templates live in `contract_templates` with:

- `template_content`: JSON contract body copied during fork.
- `version_number`: upstream template version.
- `forked_from_template_id`: optional template parent for derived templates.
- `is_platform_authored` and `is_published`: library visibility controls.

## Forking

Forking creates a new `agent_contracts` row with copied content and attribution
metadata in the contract escalation conditions. The fork is editable and remains
available even if the source template is later deleted.

## Revision Attachment

Contracts attach to registry revisions through
`agent_contracts.attached_revision_id`, which references
`registry_agent_revisions.id` with `ON DELETE SET NULL`.
