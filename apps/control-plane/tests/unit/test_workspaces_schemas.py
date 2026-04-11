from __future__ import annotations

from platform.workspaces.models import WorkspaceRole
from platform.workspaces.schemas import (
    AddMemberRequest,
    CreateGoalRequest,
    CreateWorkspaceRequest,
    UpdateSettingsRequest,
    UpdateWorkspaceRequest,
)
from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_workspace_schema_normalizes_strings() -> None:
    payload = CreateWorkspaceRequest(name="  Finance  ", description="  Planning  ")
    assert payload.name == "Finance"
    assert payload.description == "Planning"


def test_update_workspace_requires_at_least_one_field() -> None:
    with pytest.raises(ValidationError):
        UpdateWorkspaceRequest()


def test_member_schema_rejects_owner_role() -> None:
    with pytest.raises(ValidationError):
        AddMemberRequest(user_id=uuid4(), role=WorkspaceRole.owner)


def test_goal_schema_normalizes_description() -> None:
    payload = CreateGoalRequest(title="  Analyze Revenue  ", description="   ")
    assert payload.title == "Analyze Revenue"
    assert payload.description is None


def test_update_settings_requires_mutation_and_normalizes_agents() -> None:
    with pytest.raises(ValidationError):
        UpdateSettingsRequest()

    payload = UpdateSettingsRequest(subscribed_agents=[" finance:* ", "", "tools:*"])
    assert payload.subscribed_agents == ["finance:*", "tools:*"]
