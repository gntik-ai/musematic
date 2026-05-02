from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_transient_workspace_failure_defers_without_rolling_back_verification() -> None:
    accounts_service = _read("src/platform/accounts/service.py")
    retry_job = _read("src/platform/accounts/jobs/workspace_auto_create.py")
    main = _read("src/platform/main.py")

    completion = accounts_service.split("async def _complete_default_signup", maxsplit=1)[1]
    assert "except Exception as exc:" in completion
    assert "Default workspace provisioning deferred after signup verification" in completion
    assert "AccountsEventType.signup_completed" in completion

    assert "def build_workspace_auto_create_retry(app: Any)" in retry_job
    assert "SIGNUP_AUTO_CREATE_RETRY_SECONDS" in retry_job
    assert "NOT EXISTS (" in retry_job
    assert "FROM workspaces_workspaces ww" in retry_job
    assert "ww.owner_id = au.id" in retry_job
    assert "ww.is_default = true" in retry_job
    assert ".create_default_workspace(" in retry_job

    assert "build_workspace_auto_create_retry(app)" in main
