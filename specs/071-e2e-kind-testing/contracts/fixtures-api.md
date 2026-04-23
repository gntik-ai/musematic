# Pytest Fixtures API Contract

**Feature**: 071-e2e-kind-testing
**Date**: 2026-04-20
**Location**: `tests/e2e/conftest.py` + `tests/e2e/fixtures/`

All fixtures are async (pytest-asyncio mode `auto`). All sit behind a `pytest` marker system that lets suites opt in to the heavy machinery only when needed.

---

## Global constants (defined in `conftest.py`)

```python
PLATFORM_UI_URL = os.environ.get("PLATFORM_UI_URL", "http://localhost:8080")
PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
PLATFORM_WS_URL = os.environ.get("PLATFORM_WS_URL", "ws://localhost:8082")
DB_DSN = os.environ.get("E2E_DB_DSN", "postgresql://e2e_reader:…@localhost:5432/platform")
KAFKA_BOOTSTRAP = os.environ.get("E2E_KAFKA_BOOTSTRAP", "localhost:9092")
```

Environment overrides support multi-cluster testing (D-010) — the `Makefile` exports `PLATFORM_*_URL` based on `PORT_*` vars.

---

## 1. `http_client` — authenticated HTTP fixture

**Signature** (`fixtures/http_client.py`):

```python
@pytest.fixture(scope="session")
async def http_client() -> AsyncIterator[AuthenticatedAsyncClient]:
    async with AuthenticatedAsyncClient(PLATFORM_API_URL) as client:
        await client.login_as("admin@e2e.test", "e2e-test-password")
        yield client
```

**`AuthenticatedAsyncClient`** extends `httpx.AsyncClient`:

- `login_as(email, password)` — POST `/api/v1/auth/login`; stores access + refresh tokens.
- Auto-refreshes access token on 401 response once, then retries the request.
- Injects `Authorization: Bearer <access>` header on every request.
- Exposes `current_user_id`, `current_workspace_id` for assertion convenience.

**Scope**: `session` — reused across all tests in the run. A per-test `http_client_workspace_member` sibling fixture logs in as `end_user1@e2e.test` for permission-boundary tests.

---

## 2. `ws_client` — WebSocket fixture

**Signature** (`fixtures/ws_client.py`):

```python
@pytest.fixture(scope="function")
async def ws_client(http_client) -> AsyncIterator[WsClient]:
    async with WsClient(PLATFORM_WS_URL, token=http_client.access_token) as client:
        yield client
```

**`WsClient`** wraps `websockets.connect`:

- `subscribe(channel: str, topic: str)` — sends subscribe frame.
- `expect_event(channel: str, event: str, timeout: float = 10.0)` — asserts an event arrives in the channel; returns the payload.
- `drain(timeout: float)` — consumes all pending messages.

**Scope**: `function` — each test gets a fresh connection (clean subscription state).

---

## 3. `db` — direct PostgreSQL fixture (asyncpg)

**Signature** (`fixtures/db_session.py`):

```python
@pytest.fixture(scope="session")
async def db() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(DB_DSN)
    yield conn
    await conn.close()
```

**Read-only by convention**: Tests use `db.fetchrow(…)`, `db.fetchval(…)`, `db.fetch(…)` for assertion queries only. **Tests MUST NOT mutate state via `db`** — that would bypass service-layer invariants. The platform API + `/api/v1/_e2e/*` endpoints are the only legitimate write paths.

Uses a dedicated PostgreSQL user `e2e_reader` created by the Helm overlay (`values-e2e.yaml`) with `SELECT`-only grants across platform tables. Refusing write attempts at the database level enforces the read-only convention.

---

## 4. `kafka_consumer` — event assertion fixture

**Signature** (`fixtures/kafka_consumer.py`):

```python
@pytest.fixture(scope="function")
async def kafka_consumer() -> AsyncIterator[KafkaTestConsumer]:
    async with KafkaTestConsumer(KAFKA_BOOTSTRAP) as consumer:
        yield consumer
```

**`KafkaTestConsumer`** wraps `aiokafka.AIOKafkaConsumer`:

- `subscribe(topic: str)` — subscribes with `auto_offset_reset="latest"` so only post-fixture-creation events are captured.
- `expect_event(topic: str, predicate: Callable[[dict], bool], timeout: float = 10.0) -> dict` — waits for an event matching the predicate; returns payload.
- `collect(topic: str, duration: float) -> list[dict]` — collects all events on a topic over a time window.
- `expect_no_event(topic: str, predicate: Callable[[dict], bool], duration: float)` — asserts nothing matching arrives within duration.

Consumer group name is unique per test invocation (`e2e-test-{uuid}`) to avoid interfering with other test runs.

**Scope**: `function` — each test gets a fresh consumer with its own offset.

---

## 5. `workspace` — workspace factory fixture

**Signature** (`fixtures/workspace.py`):

```python
@pytest.fixture(scope="function")
async def workspace(http_client) -> AsyncIterator[Workspace]:
    ws = await http_client.post_json("/api/v1/workspaces", {"name": f"test-{uuid4().hex[:8]}"})
    yield ws
    await http_client.delete(f"/api/v1/workspaces/{ws['id']}")
```

**Behavior**: Creates a fresh `test-<hash>` workspace before the test; deletes it in teardown. Name matches the E2E scope filter (`test-%`) so `reset` endpoint cleanup can sweep it if the test crashes.

---

## 6. `agent` — agent factory fixture (parameterized)

**Signature** (`fixtures/agent.py`):

```python
@pytest.fixture(scope="function")
async def agent(http_client, workspace) -> AgentFactory:
    return AgentFactory(http_client, workspace_id=workspace["id"])
```

**`AgentFactory`**:

- `register(namespace: str, local_name: str, role_type: str, **kwargs) -> Agent` — POST `/api/v1/agents` with FQN.
- `with_certification(agent_id: str, valid_days: int = 30) -> Certification` — issues a fresh certification.
- `with_visibility(agent_id: str, patterns: list[str])` — sets visibility config.

All agents created via this factory are registered with FQN prefix `test-<workspace_hash>:` so teardown can delete them en masse.

---

## 7. `policy` — policy attachment factory

**Signature** (`fixtures/policy.py`):

```python
@pytest.fixture(scope="function")
async def policy(http_client, workspace) -> PolicyFactory:
    return PolicyFactory(http_client, workspace_id=workspace["id"])
```

**`PolicyFactory`**:

- `attach(policy_name: str, target_agent_fqn: str) -> PolicyBinding` — POST `/api/v1/policies/bindings`.
- `detach(binding_id: str)`

Seeded policies (`default-allow`, `finance-strict`, `test-budget-cap`) are available by name.

---

## 8. `mock_llm` — mock LLM control fixture

**Signature** (`fixtures/mock_llm.py`):

```python
@pytest.fixture(scope="function")
async def mock_llm(http_client) -> AsyncIterator[MockLLMController]:
    controller = MockLLMController(http_client)
    yield controller
    await controller.clear_queue()
```

**`MockLLMController`**:

- `set_response(prompt_pattern: str, response: str, streaming_chunks: list[str] | None = None)` — POST to `/api/v1/_e2e/mock-llm/set-response`.
- `set_responses(pattern_to_responses: dict[str, list[str]])` — bulk set.
- `get_calls(pattern: str | None = None, since: datetime | None = None) -> list[MockLLMCallRecord]` — read from Redis-backed ring buffer.
- `clear_queue()` — empty all queues (called in teardown).

---

## Autouse fixtures

### `ensure_seeded` (session-scoped, autouse)

Runs once per session before any test. Calls `POST /api/v1/_e2e/seed` with scope `"all"`. Idempotent — if baseline already seeded, this is a no-op skip. Fails fast with a clear error if the platform is unreachable.

```python
@pytest.fixture(scope="session", autouse=True)
async def ensure_seeded(http_client):
    response = await http_client.post_json("/api/v1/_e2e/seed", {"scope": "all"})
    assert response.status_code == 200, f"Seed failed: {response.text}"
```

### `reset_ephemeral_state` (function-scoped, autouse only for chaos + performance suites)

Runs between chaos/performance tests to ensure a clean slate. For bounded-context suites, per-test fixtures (`workspace`, `agent`, `policy`) already own their teardown so this is not needed.

---

## Helper Markers

- `@pytest.mark.slow` — test takes > 30s; excluded from `make e2e-test-fast`.
- `@pytest.mark.requires_warm_pool` — test assumes warm pool is filled; skips if not.
- `@pytest.mark.flaky(retries=2)` — tolerates one retry for genuinely transient failures (network partition ordering, rarely).

---

## Test discovery & execution

```bash
# Full suite
make e2e-test   # → pytest suites/ -v --junitxml=reports/junit.xml --html=reports/report.html

# Fast subset (skips @pytest.mark.slow)
make e2e-test-fast

# Single context
pytest suites/trust/ -v

# Single test
pytest suites/trust/test_certification_workflow.py::test_certification_lifecycle -v
```

All invocations write reports to `tests/e2e/reports/` (gitignored).
