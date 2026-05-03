"""UPD-049 refresh (102) T027 — self-review prevention guard.

Table-driven coverage for ``MarketplaceAdminService._ensure_not_self_review``.
Verifies that the guard:

* Raises ``SelfReviewNotAllowedError`` for each of the four action verbs
  (``assign``, ``claim``, ``approve``, ``reject``) when the actor is the
  submitter.
* Allows the action when the actor is NOT the submitter.
* Returns ``None`` (and does not raise) when the agent row is absent —
  callers downstream surface the not-found error, preserving the
  FR-741.10 byte-identical 404 behaviour for inaccessible public agents.

Heavy mocking — exercises the service-level branching without a live DB.
"""

from __future__ import annotations

from platform.marketplace.review_service import MarketplaceAdminService
from platform.registry.exceptions import SelfReviewNotAllowedError
from typing import Literal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

ACTIONS: list[Literal["assign", "claim", "approve", "reject"]] = [
    "assign",
    "claim",
    "approve",
    "reject",
]


def _build_service(*, submitter_id: UUID | None) -> MarketplaceAdminService:
    """Build a service whose first SELECT returns ``submitter_id`` as
    ``created_by``. Returning ``None`` simulates a missing row."""
    session = MagicMock()
    if submitter_id is None:
        result = MagicMock()
        result.mappings.return_value.first.return_value = None
    else:
        result = MagicMock()
        result.mappings.return_value.first.return_value = {"created_by": submitter_id}
    session.execute = AsyncMock(return_value=result)
    return MarketplaceAdminService(
        platform_staff_session=session,
        event_producer=None,
        notifications=None,
    )


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.asyncio
async def test_refuses_when_actor_is_submitter(
    action: Literal["assign", "claim", "approve", "reject"],
) -> None:
    actor_id = uuid4()
    service = _build_service(submitter_id=actor_id)
    with pytest.raises(SelfReviewNotAllowedError) as excinfo:
        await service._ensure_not_self_review(uuid4(), actor_id, action=action)
    error = excinfo.value
    assert error.details["action"] == action
    assert error.details["actor_user_id"] == str(actor_id)
    assert error.details["submitter_user_id"] == str(actor_id)
    assert error.status_code == 403


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.asyncio
async def test_allows_when_actor_differs_from_submitter(
    action: Literal["assign", "claim", "approve", "reject"],
) -> None:
    actor_id = uuid4()
    submitter_id = uuid4()
    assert actor_id != submitter_id
    service = _build_service(submitter_id=submitter_id)
    result = await service._ensure_not_self_review(uuid4(), actor_id, action=action)
    assert result == submitter_id


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.asyncio
async def test_returns_none_when_agent_missing(
    action: Literal["assign", "claim", "approve", "reject"],
) -> None:
    """Missing-agent path must NOT raise — caller's downstream not-found
    surfaces the right error per FR-741.10. The guard must be
    transparent in this case."""
    service = _build_service(submitter_id=None)
    result = await service._ensure_not_self_review(uuid4(), uuid4(), action=action)
    assert result is None
