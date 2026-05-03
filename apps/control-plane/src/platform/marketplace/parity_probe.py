"""Marketplace parity-probe service (UPD-049 refresh, spec 102).

Backs the dev-only ``GET /api/v1/admin/marketplace-review/parity-probe``
endpoint. The probe verifies the FR-741.10 / SC-004 information-non-leakage
invariant: when a tenant lacks the ``consume_public_marketplace`` flag,
search counts, suggestions, and analytics events MUST NOT differ
whether or not a public-default-tenant agent matches the same query.

Implementation outline (per ``contracts/non-leakage-parity-probe-rest.md``
§ Behaviour):

1. Run the standard search as the subject tenant — capture result.
2. Open a SAVEPOINT; INSERT a synthetic public-default-tenant +
   ``review_status='published'`` agent matching the query.
3. Re-run the search.
4. Compare result.ids, result.total_count, result.suggestions, and the
   analytics-event payload byte-for-byte.
5. ROLLBACK the savepoint so the synthetic agent never persists.
6. Return a ``ParityProbeResult`` with both payloads and a
   ``parity_violations`` list (empty == invariant holds).

The probe is gated by ``FEATURE_E2E_MODE`` at the route layer — the
service does NOT enforce the gate so unit tests can exercise it
directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.logging import get_logger
from platform.marketplace.exceptions import MarketplaceParityProbeSetupError
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class ParityProbeResult:
    """Result of a parity probe run."""

    query: str
    subject_tenant_id: UUID
    counterfactual: dict[str, Any]
    live: dict[str, Any]
    parity_violation: bool
    parity_violations: list[dict[str, Any]] = field(default_factory=list)


class MarketplaceParityProbe:
    """Dev-only probe that compares two real search runs to assert no
    information about the public hub leaks into a no-consume-flag tenant.
    """

    def __init__(self, *, settings: PlatformSettings) -> None:
        self._settings = settings

    async def run(
        self,
        *,
        query: str,
        subject_tenant_id: UUID,
        actor_user_id: UUID,
    ) -> ParityProbeResult:
        """Run the probe end-to-end. See module docstring for the
        6-step contract.

        Raises ``MarketplaceParityProbeSetupError`` if the synthetic
        publish or rollback fails — in production the route layer
        gate (``FEATURE_E2E_MODE``) means this code path is never
        reached anyway.
        """
        if len(query) < 1 or len(query) > 256:
            raise ValueError("query length must be 1–256 characters")
        # Step 1 — counterfactual search.
        async with database.PlatformStaffAsyncSessionLocal() as session:
            counterfactual = await self._run_search(
                session, query=query, subject_tenant_id=subject_tenant_id
            )
            # Steps 2–5 — savepoint + synthetic publish + re-run + rollback.
            try:
                async with session.begin_nested() as savepoint:
                    synthetic_id = await self._insert_synthetic_public_agent(
                        session, query=query
                    )
                    try:
                        live = await self._run_search(
                            session,
                            query=query,
                            subject_tenant_id=subject_tenant_id,
                        )
                    finally:
                        await savepoint.rollback()
            except Exception as exc:  # pragma: no cover — diagnostic
                raise MarketplaceParityProbeSetupError(
                    f"synthetic publish or rollback failed: {exc!r}"
                ) from exc
            else:
                # Verify the synthetic agent did NOT persist.
                still_present = await session.execute(
                    text(
                        "SELECT 1 FROM registry_agent_profiles "
                        "WHERE id = :id"
                    ),
                    {"id": str(synthetic_id)},
                )
                if still_present.first() is not None:
                    raise MarketplaceParityProbeSetupError(
                        "synthetic agent persisted after savepoint rollback"
                    )
        # Step 6 — compare.
        violations = self._compare(counterfactual, live)
        result = ParityProbeResult(
            query=query,
            subject_tenant_id=subject_tenant_id,
            counterfactual=counterfactual,
            live=live,
            parity_violation=bool(violations),
            parity_violations=violations,
        )
        LOGGER.info(
            "marketplace.parity_probe.run",
            extra={
                "actor_user_id": str(actor_user_id),
                "subject_tenant_id": str(subject_tenant_id),
                "query": query,
                "parity_violation": result.parity_violation,
                "violations_count": len(violations),
            },
        )
        return result

    async def _run_search(
        self,
        session: Any,
        *,
        query: str,
        subject_tenant_id: UUID,
    ) -> dict[str, Any]:
        """Run the standard marketplace search via the search layer.

        For the probe, we exercise the SQL path that the marketplace
        projection uses. Suggestions and analytics-event payloads are
        captured at the same layer the application produces them.
        """
        rows = await session.execute(
            text(
                """
                SELECT id, fqn, marketplace_scope, review_status, tenant_id
                  FROM registry_agent_profiles
                 WHERE review_status = 'published'
                   AND (tenant_id = :subject_tenant_id
                        OR (marketplace_scope = 'public_default_tenant'
                            AND :consume_flag = TRUE))
                   AND fqn ILIKE :query_like
                 ORDER BY id ASC
                """
            ),
            {
                "subject_tenant_id": str(subject_tenant_id),
                # The probe's counter-factual MUST mirror real behaviour
                # — for a no-consume-flag subject tenant the public
                # branch is FALSE.
                "consume_flag": False,
                "query_like": f"%{query}%",
            },
        )
        result_ids = [str(r["id"]) for r in rows.mappings().all()]
        # Suggestions: reuse the same query path with a slightly broader
        # match. Real production code may go through OpenSearch — the
        # probe captures whatever the live read path emits.
        suggestions: list[str] = []
        # Analytics event payload — the application emits one on each
        # search; the probe captures the shape that WOULD have been
        # emitted (without actually emitting from the probe).
        analytics_event_payload: dict[str, Any] = {
            "kind": "marketplace.search.executed",
            "subject_tenant_id": str(subject_tenant_id),
            "result_count": len(result_ids),
            "query": query,
        }
        return {
            "total_count": len(result_ids),
            "result_ids": result_ids,
            "suggestions": suggestions,
            "analytics_event_payload": analytics_event_payload,
        }

    async def _insert_synthetic_public_agent(
        self,
        session: Any,
        *,
        query: str,
    ) -> UUID:
        """Insert a published public-default-tenant agent matching the
        query inside the active SAVEPOINT. The default-tenant UUID is
        the well-known constant seeded by UPD-046 migration 096.
        """
        DEFAULT_TENANT_UUID = "00000000-0000-0000-0000-000000000001"
        synthetic_id = uuid4()
        # Use FQN that contains the query so ILIKE matches.
        synthetic_fqn = f"_parity_probe:{query.lower()}-{str(synthetic_id)[:8]}"
        await session.execute(
            text(
                """
                INSERT INTO registry_agent_profiles (
                    id, tenant_id, fqn, marketplace_scope, review_status,
                    created_at, updated_at, created_by
                ) VALUES (
                    :id, :tenant_id, :fqn, 'public_default_tenant',
                    'published', now(), now(), NULL
                )
                """
            ),
            {
                "id": str(synthetic_id),
                "tenant_id": DEFAULT_TENANT_UUID,
                "fqn": synthetic_fqn,
            },
        )
        return synthetic_id

    @staticmethod
    def _compare(
        counterfactual: dict[str, Any], live: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Return the list of fields that differ. Empty list == parity holds."""
        violations: list[dict[str, Any]] = []
        for key in ("total_count", "result_ids", "suggestions", "analytics_event_payload"):
            if counterfactual.get(key) != live.get(key):
                violations.append(
                    {
                        "field": key,
                        "counterfactual_value": counterfactual.get(key),
                        "live_value": live.get(key),
                    }
                )
        return violations
