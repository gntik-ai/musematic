# Creator Mock LLM Fallback

## Symptom

Creators see generic preview output instead of scenario-specific responses when
testing context profiles or contracts.

## Diagnosis

Check structured logs for `mock_llm.fallback_used`. A high rate means preview
inputs are not covered by `apps/control-plane/src/platform/mock_llm/fixtures.yaml`.

## Remediation

Add or update a canned response fixture:

1. Reproduce the creator preview input.
2. Compute the fixture key with `MockLLMProvider.input_hash(input_text)`.
3. Add a response entry with `input_hash`, `output_text`, and
   `completion_metadata`.
4. Keep the response deterministic and free of real provider calls.

## Verification

Run the preview again and confirm:

- `was_fallback` is `false`.
- `completion_metadata.scenario` matches the intended fixture.
- `mock_llm.fallback_used` no longer appears for the same input hash.
