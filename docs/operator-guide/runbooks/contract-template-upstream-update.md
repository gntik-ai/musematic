# Contract Template Upstream Update

## Flow

Platform-authored templates live in `contract_templates`. Creator forks copy
template content into a new editable `agent_contracts` row and preserve template
attribution metadata.

## Notification Handling

When an upstream template changes, the notification center should surface a
`creator.contract_template.upstream_updated` event with a link to review the
fork against the latest template.

## Manual Diff Resolution

1. Open the creator's forked contract.
2. Compare fork metadata with the latest platform template.
3. Apply wanted changes manually.
4. Run mock contract preview before attaching the updated contract to a
   revision.

## Verification

Confirm the fork remains editable, the original template remains published, and
the fork attribution metadata is still present after the update.
