from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(scope="session", autouse=True)
async def ensure_seeded() -> None:
    """Workspace-owner contract tests use local fixtures instead of a live seed API."""


@pytest.fixture(autouse=True)
async def reset_ephemeral_state() -> None:
    """Avoid the shared live reset fixture for local contract-only tests."""


@pytest.fixture
def workspace_with_seeded_data() -> dict[str, Any]:
    return {
        "workspace_id": "workspace-owner-e2e",
        "active_goals": 3,
        "executions_in_flight": 5,
        "agent_count": 12,
        "budget_percent": 60,
        "tags": ["science", "regulated"],
        "dlp_violations": 2,
    }


@pytest.fixture
def workspace_with_connectors() -> dict[str, Any]:
    return {
        "workspace_id": "workspace-owner-e2e",
        "connectors": ["slack", "telegram", "email", "webhook"],
        "credential_path_prefix": "secret/data/connectors/workspaces/",
    }


@pytest.fixture
def multi_member_workspace() -> dict[str, Any]:
    return {
        "workspace_id": "workspace-owner-e2e",
        "members": [
            {"user_id": "owner", "role": "owner"},
            {"user_id": "admin", "role": "admin"},
            {"user_id": "member", "role": "member"},
            {"user_id": "viewer", "role": "viewer"},
        ],
    }


@pytest.fixture
def workspace_with_visibility_grants() -> dict[str, Any]:
    return {
        "workspace_id": "workspace-owner-e2e",
        "grants_given": ["agent://science/*", "tool://lab/*"],
        "grants_received": ["workspace://shared-research"],
    }
