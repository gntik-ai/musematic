"""Workspace cascade dispatch — thin adapter over CascadeOrchestrator.

The data_lifecycle BC owns the workflow (request, grace, dispatch,
audit) but delegates the cross-store deletion machinery to
``privacy_compliance.services.cascade_orchestrator``. This module is
the only place ``CascadeOrchestrator.execute_workspace_cascade`` is
called from.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from platform.privacy_compliance.services.cascade_orchestrator import (
    CascadeOrchestrator,
)

logger = logging.getLogger(__name__)


async def dispatch_workspace_cascade(
    *,
    orchestrator: CascadeOrchestrator,
    workspace_id: UUID,
    requested_by_user_id: UUID | None,
) -> dict[str, Any]:
    """Run the workspace cascade and return the structured result.

    Caller is responsible for:
      * marking the deletion job's ``cascade_started_at`` BEFORE invocation
      * updating the workspace ``status`` to ``deleted`` AFTER success
      * persisting the tombstone reference on the deletion job
      * emitting the ``deletion.completed`` Kafka event
    """

    logger.info(
        "data_lifecycle.workspace_cascade_dispatching",
        extra={"workspace_id": str(workspace_id)},
    )
    result = await orchestrator.execute_workspace_cascade(
        workspace_id, requested_by_user_id=requested_by_user_id
    )
    logger.info(
        "data_lifecycle.workspace_cascade_completed",
        extra={
            "workspace_id": str(workspace_id),
            "errors": len(result.get("errors", [])),
            "stores_completed": len(
                [r for r in result.get("store_results", []) if r["status"] == "completed"]
            ),
        },
    )
    return result
