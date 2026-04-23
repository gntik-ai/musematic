# Pytest Fixtures + Helpers API Contract (Journeys)

**Feature**: 072-user-journey-e2e-tests
**Date**: 2026-04-21
**Location**: `tests/e2e/journeys/conftest.py` + `tests/e2e/journeys/helpers/*`

All fixtures are async (pytest-asyncio mode `auto`). Fixtures at this level compose feature 071's lower-level fixtures (`http_client`, `ws_client`, `db`, `kafka_consumer`, `mock_llm`); they do NOT duplicate them.

---

## A. Persona-scoped Client Fixtures (function-scoped)

### A.1 `admin_client(http_client, ensure_journey_personas) → AuthenticatedAsyncClient`

```python
@pytest.fixture(scope="function")
async def admin_client(http_client, ensure_journey_personas) -> AuthenticatedAsyncClient:
    client = http_client.clone()                          # fresh session, not shared with other personas
    await client.login_as("j-admin@e2e.test", "j-admin-password")
    await client.complete_mfa_if_required(totp_secret=KNOWN_ADMIN_TOTP_SECRET)
    return client
```

**Role**: `platform_admin`
**Mandatory by**: J01, J05, J06

### A.2 `creator_client(http_client, mock_github_oauth, ensure_journey_personas) → AuthenticatedAsyncClient`

```python
@pytest.fixture(scope="function")
async def creator_client(http_client, mock_github_oauth, ensure_journey_personas) -> AuthenticatedAsyncClient:
    client = http_client.clone()
    await oauth_login(client, provider="github", mock_server=mock_github_oauth,
                      login="j-creator-gh")
    return client
```

**Role**: `workspace_admin` scoped to the creator's workspace
**Mandatory by**: J02, J07

### A.3 `consumer_client(http_client, mock_google_oidc, ensure_journey_personas) → AuthenticatedAsyncClient`

**Role**: `workspace_member` (default auto-provisioned role on first OAuth login)
**Mandatory by**: J03, J04

### A.4 `operator_client(http_client, ensure_journey_personas) → AuthenticatedAsyncClient`

**Role**: `platform_operator`
**Mandatory by**: J06

### A.5 `trust_reviewer_client(http_client, ensure_journey_personas) → AuthenticatedAsyncClient`

**Role**: `trust_reviewer`
**Mandatory by**: J05

### A.6 `evaluator_client(http_client, ensure_journey_personas) → AuthenticatedAsyncClient`

**Role**: `evaluator`
**Mandatory by**: J07

### A.7 `researcher_client(http_client, ensure_journey_personas) → AuthenticatedAsyncClient`

**Role**: `researcher`
**Mandatory by**: J09

---

## B. Pre-baked State Fixtures (function-scoped)

All pre-baked fixtures take `journey_id: str` as implicit from the test module's `JOURNEY_ID` constant (read via `request.module.JOURNEY_ID`). They use the `j{NN}-test-{hash}-` prefix convention from data-model.md §5.

### B.1 `workspace_with_agents(admin_client, request) → dict`

Yields a fully configured workspace with governance chain. Shape per data-model.md §3. Teardown deletes workspace by ID cascade.

### B.2 `published_agent(admin_client, workspace_with_agents, request) → dict`

Yields a certified, published agent. Uses the `workspace_with_agents` workspace. Uploads the canned `tests/e2e/journeys/fixtures/agent_package.tar.gz` (a minimal valid agent package).

### B.3 `workspace_with_goal_ready(admin_client, workspace_with_agents, request) → dict`

Yields a workspace with 4 subscribed agents (3 relevant + 1 irrelevant by response-decision config) and a goal in READY state.

### B.4 `running_workload(admin_client, workspace_with_agents, request) → dict`

Yields a fleet + 2 running executions + a filled warm pool + 3 queued executions. Used exclusively by J06.

### B.5 Autouse: `ensure_journey_personas`

Session-scoped, autouse. Idempotently creates 7 persona users (one per persona) via direct seeder import. No-op if already created.

### B.6 Autouse: `cleanup_journey_resources(request)`

Function-scoped, autouse. Runs teardown after each journey by issuing:
```
POST /api/v1/_e2e/reset
{ "scope": "workspaces", "filter": "j{NN}-test-{hash}-%" }
```
Uses the JOURNEY_ID + per-test hash captured in the fixture.

---

## C. Workflow Helper Surface (`tests/e2e/journeys/helpers/`)

All helpers take an `AuthenticatedAsyncClient` as first argument and a `journey_id: str` as either second argument or kwarg. They are plain async functions — NOT pytest fixtures.

### C.1 `oauth_login(client, provider: str, mock_server: str, login: str) → AuthenticatedAsyncClient`

Drives an OAuth login flow against an in-cluster mock OAuth server (see contracts/oauth-mock.md).

```python
async def oauth_login(
    client: AuthenticatedAsyncClient,
    provider: Literal["google", "github"],
    mock_server: str,                      # URL from mock_google_oidc / mock_github_oauth fixture
    login: str,                            # username / email key recognized by the mock
) -> AuthenticatedAsyncClient:
    """
    1. Calls GET /api/v1/auth/{provider}/authorize to get the redirect URL
    2. Follows redirect to mock_server; mock returns authorization code
    3. Calls /api/v1/auth/{provider}/callback?code=... with platform
    4. Platform exchanges code for tokens via mock_server's /token endpoint
    5. Platform issues platform JWT pair
    6. Returns authenticated client
    """
```

### C.2 `register_full_agent(client, journey_id: str, namespace: str, local_name: str, role_type: str, **manifest_kwargs) → dict`

Registers an agent with a complete manifest including FQN, purpose, approach, visibility patterns, and tools. Automatically prefixes `namespace` and `local_name` with `j{journey_id}-test-{hash}-`.

Returns `{"fqn": "...", "id": "...", "revision_id": "..."}`.

### C.3 `certify_agent(client, agent_id: str, reviewer_client: AuthenticatedAsyncClient | None = None, evidence: list[str] | None = None) → dict`

Submits certification request. If `reviewer_client` is provided (trust_reviewer), approves as that reviewer; otherwise the admin client self-approves.

Returns `{"certification_id": "...", "status": "active"}`.

### C.4 `create_governance_chain(client, workspace_id: str, observer_fqn: str, judge_fqn: str, enforcer_fqn: str) → dict`

Binds three agents into an Observer→Judge→Enforcer chain for the given workspace. Validates each agent has the required role type. Returns the binding IDs.

### C.5 `wait_for_execution(client, execution_id: str, timeout: float = 60.0, expected_states: list[str] = ["completed"]) → dict`

Polls `GET /api/v1/executions/{id}` every 1 s until `status in expected_states` or timeout. Returns the final execution record. Raises `AssertionError` on timeout with the last observed state.

### C.6 `subscribe_ws(ws_client, channel: str, topic: str) → AsyncIterator[dict]`

Context-manager wrapper around feature 071's `WsClient.subscribe(channel, topic)` that yields events and provides `.received_events` list for post-hoc assertion. Used as:

```python
async with subscribe_ws(ws_client, "conversations", f"conversations/{conv_id}") as sub:
    async for event in sub.events():
        if event["type"] == "execution.completed":
            break
    assert any(e["type"] == "reasoning.trace.step" for e in sub.received_events)
```

### C.7 `attach_contract(client, agent_id: str, max_response_time_ms: int, min_accuracy: float) → dict` (bonus helper for J05)

Attaches a behavioral contract to an agent. Returns contract binding ID.

### C.8 `@journey_step(description: str)` (context manager)

Records a narrative step for the HTML report. Captures start/end timestamps, catches exceptions to attribute failures to the specific step, and emits a `JourneyStepRecord` (see data-model.md §4).

```python
with journey_step("Admin enrolls MFA"):
    response = await admin_client.post("/api/v1/auth/mfa/enroll", json={"type": "totp"})
    assert response.status_code == 200
    totp_secret = response.json()["secret"]
```

---

## D. Module-level constants (per journey)

Every `test_j{NN}_*.py` file exports:

```python
JOURNEY_ID = "j{NN}"                     # e.g. "j01"
TIMEOUT_SECONDS = {180|300|600}          # per-journey timeout (D-008)
CROSS_CONTEXT_INVENTORY = [              # backup for AST parsing; primary source is the # Cross-context inventory: comment
    "auth", "workspaces", ...
]
```

The meta-test `test_journey_structure.py` prefers the `# Cross-context inventory:` comment (parsed from AST) but falls back to `CROSS_CONTEXT_INVENTORY` module constant if the comment is malformed.

---

## E. Pytest markers registered in `tests/e2e/journeys/conftest.py`

```python
def pytest_configure(config):
    config.addinivalue_line("markers", "journey: marks a user journey test")
    config.addinivalue_line("markers", "j01_admin: admin bootstrap journey")
    config.addinivalue_line("markers", "j02_creator: creator to publication journey")
    config.addinivalue_line("markers", "j03_consumer: consumer discovery and execution journey")
    config.addinivalue_line("markers", "j04_workspace_goal: collaborative workspace goal journey")
    config.addinivalue_line("markers", "j05_trust: trust officer governance journey")
    config.addinivalue_line("markers", "j06_operator: operator incident response journey")
    config.addinivalue_line("markers", "j07_evaluator: evaluation and improvement journey")
    config.addinivalue_line("markers", "j08_external: A2A and MCP integration journey")
    config.addinivalue_line("markers", "j09_discovery: scientific discovery journey")
```

---

## F. Test execution surface

```bash
# Full journey suite (parallel, 3 workers)
make e2e-journeys
# → pytest journeys/ -n 3 --dist=loadfile -v -m journey --junitxml=reports/journeys-junit.xml --html=reports/journeys-report.html

# Single journey by marker
make e2e-j03
# → pytest journeys/ -v -m j03_consumer --junitxml=reports/j03-junit.xml

# All journeys by marker
pytest journeys/ -v -m journey

# Meta-test only
pytest journeys/test_journey_structure.py -v
```

All invocations write reports to `tests/e2e/reports/` (gitignored; captured by feature 071's CI artifact upload).
