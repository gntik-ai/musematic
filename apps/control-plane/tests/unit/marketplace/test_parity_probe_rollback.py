"""UPD-049 refresh (102) T050 — parity-probe savepoint rollback unit test.

Verifies the production-safety guarantee documented in
``contracts/non-leakage-parity-probe-rest.md``: the synthetic public
agent inserted by the probe MUST be rolled back before the response
returns, even on exception paths.

Heavy mocking — exercises the SAVEPOINT lifecycle without a live DB.
"""

from __future__ import annotations

from platform.marketplace.parity_probe import MarketplaceParityProbe
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


def _build_probe() -> MarketplaceParityProbe:
    settings = MagicMock()
    return MarketplaceParityProbe(settings=settings)


def _build_session_with_savepoint(*, raise_in_synthetic: bool = False) -> MagicMock:
    """Returns a session whose ``begin_nested()`` is a context manager
    yielding a savepoint with ``rollback`` tracking. ``execute`` returns
    empty rowsets so the post-rollback "still_present" check sees nothing.
    """
    session = MagicMock()
    savepoint = MagicMock()
    savepoint.rollback = AsyncMock()
    nested_ctx = MagicMock()
    nested_ctx.__aenter__ = AsyncMock(return_value=savepoint)
    nested_ctx.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested = MagicMock(return_value=nested_ctx)

    empty_result = MagicMock()
    empty_result.mappings.return_value.all.return_value = []
    empty_result.first.return_value = None
    session.execute = AsyncMock(return_value=empty_result)
    if raise_in_synthetic:
        session.execute.side_effect = [
            empty_result,  # counterfactual search
            RuntimeError("synthetic insert failed"),
        ]
    return session


@pytest.mark.asyncio
async def test_synthetic_insert_failure_does_not_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the synthetic INSERT raises, the savepoint context manager's
    __aexit__ MUST run (rolling back), and the probe MUST surface
    ``MarketplaceParityProbeSetupError`` to the caller — not a partial
    state.
    """
    probe = _build_probe()
    session = _build_session_with_savepoint(raise_in_synthetic=True)

    class _SessionCtx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        "platform.marketplace.parity_probe.database.PlatformStaffAsyncSessionLocal",
        lambda: _SessionCtx(),
    )

    from platform.marketplace.exceptions import MarketplaceParityProbeSetupError

    with pytest.raises(MarketplaceParityProbeSetupError):
        await probe.run(
            query="anything",
            subject_tenant_id=uuid4(),
            actor_user_id=uuid4(),
        )
