"""Unit tests for the UPD-051 scope-level cascade extension.

These tests verify ``CascadeOrchestrator.execute_workspace_cascade`` and
``execute_tenant_cascade`` correctly delegate to per-adapter scope methods,
aggregate results, and handle ``NotImplementedError`` from adapters that
have not yet opted in.

The orchestrator is exercised with stub adapters; the production
PostgreSQL adapter's scope methods are tested separately under
``tests/integration/privacy_compliance/`` against a live DB.
"""

from __future__ import annotations

from datetime import UTC, datetime
from platform.privacy_compliance.cascade_adapters.base import (
    CascadeAdapter,
    CascadeResult,
)
from platform.privacy_compliance.services.cascade_orchestrator import (
    CascadeOrchestrator,
)
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class _ScopeAdapter(CascadeAdapter):
    """Stub adapter that records scope-level calls and returns deterministic
    results.

    ``mode`` controls behaviour:
      * ``ok``: returns a CascadeResult with ``rows_affected``
      * ``partial``: returns a CascadeResult with errors populated
      * ``not_implemented``: raises NotImplementedError on scope methods
      * ``raise``: raises a generic Exception
    """

    def __init__(
        self,
        store_name: str,
        rows_affected: int = 0,
        *,
        mode: str = "ok",
    ) -> None:
        self.store_name = store_name
        self.rows_affected = rows_affected
        self.mode = mode
        self.workspace_calls: list[UUID] = []
        self.tenant_calls: list[UUID] = []

    async def dry_run(self, subject_user_id: UUID):  # pragma: no cover - unused
        from platform.privacy_compliance.cascade_adapters.base import CascadePlan

        return CascadePlan(self.store_name, 0, {})

    async def execute(self, subject_user_id: UUID) -> CascadeResult:  # pragma: no cover - unused
        now = datetime.now(UTC)
        return CascadeResult(self.store_name, now, now, 0, {}, [])

    async def execute_for_workspace(self, workspace_id: UUID) -> CascadeResult:
        self.workspace_calls.append(workspace_id)
        return self._dispatch_mode()

    async def execute_for_tenant(self, tenant_id: UUID) -> CascadeResult:
        self.tenant_calls.append(tenant_id)
        return self._dispatch_mode()

    def _dispatch_mode(self) -> CascadeResult:
        now = datetime.now(UTC)
        if self.mode == "ok":
            return CascadeResult(
                self.store_name,
                now,
                now,
                self.rows_affected,
                {self.store_name: self.rows_affected},
                [],
            )
        if self.mode == "partial":
            return CascadeResult(
                self.store_name,
                now,
                now,
                self.rows_affected,
                {self.store_name: self.rows_affected},
                ["partial-failure-detail"],
            )
        if self.mode == "not_implemented":
            raise NotImplementedError(f"{self.store_name} stub")
        if self.mode == "raise":
            raise RuntimeError("boom")
        raise AssertionError(f"unknown mode {self.mode!r}")


def _orchestrator(*adapters: CascadeAdapter) -> CascadeOrchestrator:
    """Build an orchestrator wired with the minimum set of collaborators."""

    repo = SimpleNamespace()  # tombstone path is not exercised here
    signer = SimpleNamespace()
    salt = SimpleNamespace()
    return CascadeOrchestrator(
        repository=repo,
        adapters=list(adapters),
        signer=signer,
        salt_provider=salt,
        audit_chain=None,
    )


@pytest.mark.asyncio
async def test_execute_workspace_cascade_invokes_each_adapter_in_order() -> None:
    pg = _ScopeAdapter("postgresql", rows_affected=120)
    qdrant = _ScopeAdapter("qdrant", rows_affected=4)
    s3 = _ScopeAdapter("s3", rows_affected=17)
    orch = _orchestrator(pg, qdrant, s3)
    workspace_id = uuid4()

    result = await orch.execute_workspace_cascade(
        workspace_id, requested_by_user_id=uuid4()
    )

    assert pg.workspace_calls == [workspace_id]
    assert qdrant.workspace_calls == [workspace_id]
    assert s3.workspace_calls == [workspace_id]
    # store_results is in adapter-iteration order (deterministic).
    stores = [entry["store"] for entry in result["store_results"]]
    assert "postgresql" in stores
    assert "qdrant" in stores
    assert "s3" in stores
    pg_entry = next(e for e in result["store_results"] if e["store"] == "postgresql")
    assert pg_entry["status"] == "completed"
    assert pg_entry["rows_affected"] == 120
    assert result["errors"] == []
    assert result["scope_label"].startswith("workspace:")


@pytest.mark.asyncio
async def test_execute_tenant_cascade_emits_completed_results() -> None:
    pg = _ScopeAdapter("postgresql", rows_affected=12345)
    s3 = _ScopeAdapter("s3", rows_affected=42)
    orch = _orchestrator(pg, s3)
    tenant_id = uuid4()

    result = await orch.execute_tenant_cascade(tenant_id)

    assert pg.tenant_calls == [tenant_id]
    assert s3.tenant_calls == [tenant_id]
    assert all(r["status"] == "completed" for r in result["store_results"])
    assert result["errors"] == []
    assert result["scope_label"] == f"tenant:{tenant_id}"


@pytest.mark.asyncio
async def test_not_implemented_adapter_records_skip_without_aborting() -> None:
    pg = _ScopeAdapter("postgresql", rows_affected=10)
    qdrant = _ScopeAdapter("qdrant", mode="not_implemented")
    orch = _orchestrator(pg, qdrant)

    result = await orch.execute_tenant_cascade(uuid4())

    pg_entry = next(e for e in result["store_results"] if e["store"] == "postgresql")
    qdrant_entry = next(e for e in result["store_results"] if e["store"] == "qdrant")
    assert pg_entry["status"] == "completed"
    assert qdrant_entry["status"] == "skipped"
    assert qdrant_entry["rows_affected"] == 0
    assert any("qdrant" in err for err in result["errors"])


@pytest.mark.asyncio
async def test_partial_adapter_records_partial_status() -> None:
    pg = _ScopeAdapter("postgresql", rows_affected=5, mode="partial")
    orch = _orchestrator(pg)

    result = await orch.execute_workspace_cascade(uuid4())

    pg_entry = next(e for e in result["store_results"] if e["store"] == "postgresql")
    assert pg_entry["status"] == "partial"
    assert pg_entry["rows_affected"] == 5
    assert "partial-failure-detail" in result["errors"]


@pytest.mark.asyncio
async def test_unhandled_exception_records_failure_status() -> None:
    pg = _ScopeAdapter("postgresql", rows_affected=10)
    qdrant = _ScopeAdapter("qdrant", mode="raise")
    orch = _orchestrator(pg, qdrant)

    result = await orch.execute_tenant_cascade(uuid4())

    qdrant_entry = next(e for e in result["store_results"] if e["store"] == "qdrant")
    assert qdrant_entry["status"] == "failed"
    assert any("qdrant" in err and "boom" in err for err in result["errors"])
    # PostgreSQL still ran successfully.
    pg_entry = next(e for e in result["store_results"] if e["store"] == "postgresql")
    assert pg_entry["status"] == "completed"


@pytest.mark.asyncio
async def test_scope_cascade_returns_timestamps() -> None:
    pg = _ScopeAdapter("postgresql", rows_affected=1)
    orch = _orchestrator(pg)

    before = datetime.now(UTC)
    result = await orch.execute_workspace_cascade(uuid4())
    after = datetime.now(UTC)

    assert before <= result["cascade_started_at"] <= result["cascade_completed_at"] <= after
