# Rule 50 Verification

Date: 2026-05-01

## Scope

Verified the UPD-044 creator-preview implementation against Rule 50:

- Context profile previews default to `MockLLMService` via
  `ContextEngineeringService.preview_retrieval()`.
- Contract previews default to `MockLLMService` via
  `ContractService.preview_contract(use_mock=True)`.
- Contract preview rejects `use_mock=false` unless `cost_acknowledged=true`.
- The new `MockLLMProvider` uses local YAML fixtures and does not load provider
  credentials or call model-router clients.

## Evidence

- `apps/control-plane/src/platform/mock_llm/provider.py` hashes input with
  SHA-256 first 16 hex chars and loads canned responses from `fixtures.yaml`.
- `apps/control-plane/tests/mock_llm/test_provider.py` covers deterministic
  fixture lookup, fallback logging, fixture loading, and schema validation.
- `apps/control-plane/tests/context_engineering/test_preview.py` asserts profile
  preview invokes the mock service and does not increment a real-LLM counter.
- `apps/control-plane/tests/trust/test_contract_preview.py` asserts mock default,
  real-LLM acknowledgement rejection, and acknowledged opt-in behavior.
- `apps/control-plane/src/platform/context_engineering/service.py` emits
  `creator.context_profile.preview_executed`.
- `apps/control-plane/src/platform/trust/contract_service.py` emits
  `creator.contract.preview_executed` and conditionally emits
  `creator.contract.real_llm_preview_used`.

## Local Run

Commands run:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/mock_llm/test_provider.py \
  tests/context_engineering/test_versioning.py \
  tests/context_engineering/test_preview.py \
  tests/trust/test_contract_preview.py \
  tests/trust/test_contract_templates.py \
  tests/trust/test_attach_to_revision.py \
  -q
```

Result: 29 passed. The initial ambient `pytest` run was blocked by missing
`grpc`; running through `uv` used the control-plane project environment.

## Remaining Environment-Scope Verification

Endpoint-level Rule 50 verification against a live API is covered by the
kind/matrix E2E tasks. In this local sandbox, those tests stop before exercising
the feature because no platform API is available at `http://localhost:8081`.
