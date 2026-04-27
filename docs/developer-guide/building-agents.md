# Agents

Agents may define a default model binding through `default_model_binding`. The value must use the
catalogue binding format:

```json
{
  "default_model_binding": "openai:gpt-4o"
}
```

The field is accepted on `PATCH /api/v1/agents/{id}`. When set, the registry validates that the
target model exists in the catalogue and is not blocked. Invalid bindings are rejected with three
approved alternatives selected from purpose and tier similarity.

Runtime behavior:

- Workflows may override the default with a step-level binding.
- Agents without a default binding fail fast until an admin sets one.
- Deprecated bindings continue to run during migration windows.
- Blocked bindings fail before provider dispatch.

Model cards are part of certification pre-flight. A certification request for an agent whose bound
model has no card is blocked with reason `model_card_missing`.

## Related Workflows

Feature 075 introduced model catalog fallback and the router checks that validate `default_model_binding`. Feature 086's Admin Workbench exposes the model-catalog administration page where platform admins approve, block, deprecate, and re-approve models. Creators should check both the catalog state and fallback policy before publishing an agent revision.
