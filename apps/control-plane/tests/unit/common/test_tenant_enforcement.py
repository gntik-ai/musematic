from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.tenant_enforcement import record_tenant_enforcement_violation
from uuid import UUID


class _Session:
    def __init__(self) -> None:
        self.executed: list[tuple[str, dict[str, object]]] = []
        self.flushed = False

    async def execute(self, statement, parameters):
        self.executed.append((str(statement), dict(parameters)))

    async def flush(self) -> None:
        self.flushed = True


async def test_record_tenant_enforcement_violation_writes_in_lenient_mode() -> None:
    session = _Session()
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")

    recorded = await record_tenant_enforcement_violation(
        session,  # type: ignore[arg-type]
        table_name="workspaces_workspaces",
        query_text="WorkspacesRepository.get_workspace_by_id",
        expected_tenant_id=tenant_id,
        observed_violation="workspace was not visible",
        settings=PlatformSettings(PLATFORM_TENANT_ENFORCEMENT_LEVEL="lenient"),
    )

    assert recorded is True
    assert session.flushed is True
    assert len(session.executed) == 1
    assert session.executed[0][1] == {
        "table_name": "workspaces_workspaces",
        "query_text": "WorkspacesRepository.get_workspace_by_id",
        "expected_tenant_id": tenant_id,
        "observed_violation": "workspace was not visible",
    }


async def test_record_tenant_enforcement_violation_skips_in_strict_mode() -> None:
    session = _Session()

    recorded = await record_tenant_enforcement_violation(
        session,  # type: ignore[arg-type]
        table_name="workspaces_workspaces",
        query_text="WorkspacesRepository.get_workspace_by_id",
        expected_tenant_id=None,
        observed_violation="workspace was not visible",
        settings=PlatformSettings(PLATFORM_TENANT_ENFORCEMENT_LEVEL="strict"),
    )

    assert recorded is False
    assert session.flushed is False
    assert session.executed == []
