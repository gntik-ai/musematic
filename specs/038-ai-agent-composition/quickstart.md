# Quickstart: AI-Assisted Agent Composition

## Prerequisites

- Python 3.12+, PostgreSQL 16
- Existing bounded contexts operational: registry (021), policy (028), connectors (025)
- Alembic migration chain up to 037 applied
- LLM API endpoint configured (see Key Configuration below)

## New Dependencies

No new Python packages required. All dependencies already in the tech stack:
- `httpx 0.27+` — LLM API calls (already in stack)
- `aiokafka 0.11+` — Kafka event publishing (already in stack)
- `SQLAlchemy 2.x async` — ORM (already in stack)

## Running the Context

```bash
cd apps/control-plane

# Apply migration
make migrate

# Run with composition profile
RUNTIME_PROFILE=composition python -m platform.main
```

The `composition` runtime profile starts:
1. FastAPI app with `/api/v1/compositions` router mounted
2. Kafka producer for `composition.events` topic

No APScheduler tasks (composition is on-demand, not scheduled).

## Running Tests

```bash
cd apps/control-plane
pytest tests/unit/composition/ -v
pytest tests/integration/composition/ -v
```

Integration tests use:
- SQLite in-memory (local mode fallback)
- Mock LLM responses (pre-recorded JSON fixtures)
- In-process dict mock for service interfaces

## Project Structure

```text
apps/control-plane/src/platform/composition/
├── __init__.py
├── models.py             # 5 PostgreSQL tables
├── schemas.py            # Pydantic request/response schemas
├── service.py            # CompositionService (main orchestration)
├── repository.py         # Database access (insert-only audit entries)
├── router.py             # FastAPI router (/api/v1/compositions)
├── events.py             # Kafka event definitions + CompositionEventPublisher
├── exceptions.py         # CompositionError hierarchy
├── dependencies.py       # FastAPI dependency injection
├── llm/
│   ├── __init__.py
│   └── client.py         # LLMCompositionClient: prompt building + httpx call
├── generators/
│   ├── __init__.py
│   ├── agent.py          # AgentBlueprintGenerator: agent prompt + response parser
│   └── fleet.py          # FleetBlueprintGenerator: fleet prompt + response parser
└── validation/
    ├── __init__.py
    └── validator.py      # BlueprintValidator: 5 concurrent constraint checks

migrations/versions/
└── 038_ai_agent_composition.py   # All 5 PostgreSQL tables

tests/unit/composition/
├── test_llm_client.py
├── test_agent_generator.py
├── test_fleet_generator.py
├── test_blueprint_validator.py
├── test_audit_recorder.py
└── test_composition_service.py

tests/integration/composition/
├── test_agent_blueprint_endpoints.py
├── test_fleet_blueprint_endpoints.py
├── test_validation_endpoints.py
└── test_audit_endpoints.py
```

## Key Configuration (PlatformSettings additions)

```python
# LLM
COMPOSITION_LLM_API_URL: str = "http://localhost:8080/v1/chat/completions"
COMPOSITION_LLM_MODEL: str = "claude-opus-4-6"
COMPOSITION_LLM_TIMEOUT_SECONDS: float = 25.0  # <30s requirement with 5s buffer
COMPOSITION_LLM_MAX_RETRIES: int = 2

# Blueprint limits
COMPOSITION_DESCRIPTION_MAX_CHARS: int = 10000
COMPOSITION_LOW_CONFIDENCE_THRESHOLD: float = 0.5

# Validation
COMPOSITION_VALIDATION_TIMEOUT_SECONDS: float = 10.0
```

## LLM API Note

The composition service calls an OpenAI-compatible chat completions endpoint. Any model that supports JSON mode (structured output) works:
- `claude-opus-4-6` — production default (highest quality)
- `claude-sonnet-4-6` — faster, lower cost (acceptable for development)

The API endpoint and model are workspace-agnostic platform configuration. No per-workspace LLM API keys are supported in v1 (single platform LLM endpoint).
