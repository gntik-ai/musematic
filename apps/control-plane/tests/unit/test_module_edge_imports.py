from __future__ import annotations

from platform import connectors
from platform.context_engineering.drift_monitor import DriftMonitorTask
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def test_connectors_module_lazy_getattr_exports_service_dependency() -> None:
    assert connectors.__getattr__("get_connectors_service").__name__ == "get_connectors_service"
    with pytest.raises(AttributeError):
        connectors.__getattr__("missing")


@pytest.mark.asyncio
async def test_drift_monitor_task_delegates_to_service() -> None:
    service = SimpleNamespace(run_drift_analysis=AsyncMock(return_value=3))
    assert await DriftMonitorTask(service).run() == 3
