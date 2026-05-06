# Contract — Journey Test Template

Every new journey under `tests/e2e/journeys/test_jNN_*.py` MUST follow this structure. The shape is enforced by the `test_helpers_contract.py` smoke test (UPD-038) which every PR runs.

## File layout

```python
"""J{NN} {Title} — UPD-054 ({optional FR ref})

{1–2 sentence description of the user value the journey validates.}

Cross-BC links: {one-line list of the BCs this journey crosses, satisfying
constitution rule 25}.
"""
from __future__ import annotations

import os

import pytest

from tests.e2e.fixtures.tenants import provision_enterprise
from tests.e2e.fixtures.users import synthetic_user
# ... other fixtures as needed

pytestmark = [
    pytest.mark.journey,                  # required
    pytest.mark.j{NN},                    # required, used by --select=j{NN}
    pytest.mark.skipif(
        os.environ.get("RUN_J{NN}", "1") != "1",   # optional opt-out
        reason="Set RUN_J{NN}=0 to skip in local runs.",
    ),
    pytest.mark.timeout(480),             # required — 8-min hard ceiling
]


@pytest.mark.asyncio
async def test_j{NN}_happy_path(
    super_admin_client,
    db_session,
    kafka_consumer,
    audit_chain,
) -> None:
    """The primary acceptance scenario.

    Each journey has at least one happy-path test function. Sub-scenarios
    (e.g., J28 carries five) are sibling test functions in the same file.
    """
    # Arrange: fixtures.
    async with provision_enterprise(super_admin_client=super_admin_client) as tenant:
        admin = await synthetic_user(tenant=tenant, role="tenant_admin", mfa_enrolled=True)

        # Act: drive the user-facing flow via the public API.
        ...

        # Assert: against the public surface (REST, WS, audit chain, Kafka events).
        ...
```

## Hard rules

1. **`pytest.mark.journey` is required.** The CI `journey-tests (saas-pass)` matrix entry filters on `-m journey`; missing the marker means the test silently never runs.
2. **`pytest.mark.j{NN}` is required.** Lets `--select=j{NN}` (a future flag) and `pytest -k j22` work consistently.
3. **`pytest.mark.timeout(480)` is required.** Without the 8-minute hard timeout a stuck fixture can wedge a CI runner indefinitely.
4. **Fixtures are the only setup mechanism.** No `setUp` / `tearDown`; no module-level state. This keeps `pytest-xdist` parallelism safe.
5. **All assertions go through public APIs or the inspection fixtures.** Direct PostgreSQL writes are forbidden; reads via `db_session` are allowed but discouraged in favour of REST inspection.
6. **Artefact-bundle hooks are automatic.** The session conftest's `pytest_runtest_makereport` hook captures Playwright screenshots, HARs, audit-chain slices, and tenant-state dumps on every test failure. Journey authors MUST NOT call `playwright_capture()` or similar manually — duplicate captures clutter the bundle.
7. **Cleanup is fixture-owned.** A journey author who needs ad-hoc cleanup writes a fixture and lets the framework's existing teardown machinery run it.
8. **Cross-BC links MUST appear in the docstring.** Constitution rule 25 demands every E2E journey crosses ≥ 2 BCs; the docstring header documents which.

## Sub-scenario pattern (for J28-style multi-state journeys)

When a journey covers multiple flows that share fixtures (e.g., J28 covers upgrade, overage, payment failure, recovery, downgrade, cancellation, reactivation), use one test function per scenario, sharing fixtures via `pytest`'s `@pytest.fixture(scope="module")`:

```python
@pytest.fixture(scope="module")
async def j28_pro_workspace(super_admin_client):
    """Shared module-scope fixture: a Pro workspace with an active card."""
    async with provision_enterprise(...) as tenant:
        ...
        yield tenant


@pytest.mark.asyncio
async def test_j28_upgrade_free_to_pro(j28_pro_workspace, ...): ...

@pytest.mark.asyncio
async def test_j28_overage_authorize_then_resume(j28_pro_workspace, ...): ...

@pytest.mark.asyncio
async def test_j28_payment_failure_then_recovery(j28_pro_workspace, ...): ...
```

Module-scope is acceptable because each sub-scenario is independent; the fixture is rebuilt for the *next* test file.

## Cross-references

- The smoke test enforcing this template: `tests/e2e/journeys/test_helpers_contract.py` (UPD-038).
- Existing journeys exemplifying the convention: `tests/e2e/journeys/test_j01_admin_bootstrap.py`, `tests/e2e/journeys/test_j06_operator_incident_response.py`.
- Failure-artefact pipeline: contract `promotion-gate.md` § "Artefact bundle (SC-005)".
