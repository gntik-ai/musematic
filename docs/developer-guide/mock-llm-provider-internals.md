# Mock LLM Provider Internals

The creator-preview mock provider is implemented in
`platform.mock_llm`. It is deterministic and never calls a real model provider.

## Fixture Format

Fixtures live in `apps/control-plane/src/platform/mock_llm/fixtures.yaml`:

```yaml
responses:
  - input_hash: "7da3ea817b92643a"
    output_text: "Mock support response..."
    completion_metadata:
      scenario: "customer-support"
      model: "mock-creator-preview-v1"
fallback:
  input_hash: "a99f7a6307645e93"
  output_text: "Mock fallback response..."
  completion_metadata:
    scenario: "generic-fallback"
```

## Hashing

`MockLLMProvider.input_hash()` computes SHA-256 over the input text and uses the
first 16 hex characters as the lookup key.

## Adding Fixtures

Add a response for common creator-preview inputs, keep output deterministic, and
include enough metadata for test assertions. Unknown inputs return the fallback
and log `mock_llm.fallback_used`.
