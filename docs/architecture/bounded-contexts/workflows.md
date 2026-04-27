# Workflows

Workflows owns workflow definitions, versions, triggers, and compilation into executable intermediate representation.

Primary entities include workflow definitions, workflow versions, trigger definitions, and compiler diagnostics. The REST surface is rooted at `/api/v1/workflows`. Events announce trigger and definition changes.

Workflow compiler errors use stable codes such as `WORKFLOW_YAML_INVALID`, `WORKFLOW_SCHEMA_INVALID`, and `WORKFLOW_DUPLICATE_STEP`.
