from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from platform.common.exceptions import ValidationError
from platform.interactions.events import (
    InteractionStartedPayload,
    publish_interaction_started,
)
from platform.interactions.exceptions import (
    AttentionRequestNotFoundError,
    BranchNotFoundError,
    InteractionNotFoundError,
)
from platform.interactions.router import _identity, _workspace_id
from platform.interactions.schemas import BranchMerge, ConversationUpdate, InteractionTransition
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError


def test_interactions_router_helpers_resolve_identity_and_workspace_id() -> None:
    user_workspace_id = uuid4()
    header_workspace_id = uuid4()
    role_workspace_id = uuid4()

    assert (
        _workspace_id(
            SimpleNamespace(headers={"X-Workspace-ID": str(header_workspace_id)}),
            {"workspace_id": str(user_workspace_id)},
        )
        == user_workspace_id
    )
    assert (
        _workspace_id(
            SimpleNamespace(headers={"X-Workspace-ID": str(header_workspace_id)}),
            {},
        )
        == header_workspace_id
    )
    assert (
        _workspace_id(
            SimpleNamespace(headers={}),
            {"roles": [{"workspace_id": str(role_workspace_id)}]},
        )
        == role_workspace_id
    )

    with pytest.raises(ValidationError):
        _workspace_id(SimpleNamespace(headers={}), {})

    assert (
        _identity(
            {"sub": "user-1"},
            SimpleNamespace(headers={"X-Agent-FQN": "ops:agent"}),
        )
        == "ops:agent"
    )
    assert (
        _identity(
            {"agent_fqn": "stored:agent", "sub": "user-1"},
            SimpleNamespace(headers={}),
        )
        == "stored:agent"
    )
    assert _identity({"sub": "user-1"}, SimpleNamespace(headers={})) == "user-1"

    with pytest.raises(ValidationError):
        _identity({}, SimpleNamespace(headers={}))


def test_interactions_contracts_validate_schemas_and_errors() -> None:
    with pytest.raises(PydanticValidationError):
        ConversationUpdate()

    with pytest.raises(PydanticValidationError):
        InteractionTransition(trigger="fail")

    assert BranchMerge(conflict_resolution="   ").conflict_resolution is None

    interaction_error = InteractionNotFoundError(uuid4())
    branch_error = BranchNotFoundError(uuid4())
    attention_error = AttentionRequestNotFoundError(uuid4())

    assert interaction_error.code == "INTERACTION_NOT_FOUND"
    assert branch_error.code == "BRANCH_NOT_FOUND"
    assert attention_error.code == "ATTENTION_REQUEST_NOT_FOUND"


@pytest.mark.asyncio
async def test_interactions_event_publish_is_noop_without_producer() -> None:
    await publish_interaction_started(
        None,
        InteractionStartedPayload(
            interaction_id=uuid4(),
            conversation_id=uuid4(),
            workspace_id=uuid4(),
            goal_id=None,
            created_by="user-1",
        ),
        CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=uuid4(),
            conversation_id=uuid4(),
            interaction_id=uuid4(),
            execution_id=None,
            goal_id=None,
        ),
    )
