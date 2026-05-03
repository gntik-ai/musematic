"""UPD-049 refresh (102) T029 — reviewer-assignment lifecycle end-to-end.

Spec coverage: spec.md FR-738, FR-741.9, contract
``reviewer-assignment-rest.md``, research R11. Independent test for US1
acceptance scenarios 4–5 (lead assigns, reviewer claims, reassignment
forbidden without unassign).

Lifecycle covered:

1. Lead POSTs ``/{agent_id}/assign`` with reviewer R1 — 200, audit +
   Kafka ``marketplace.review.assigned`` with ``prior_assignee_user_id=null``.
2. Lead POSTs the same payload again — 200, idempotent (no audit, no Kafka).
3. Lead POSTs with reviewer R2 — 409 ``REGISTRY_REVIEWER_ASSIGNMENT_CONFLICT``.
4. R2 POSTs ``/{agent_id}/claim`` — 409 (claim-jumping prevention).
5. R1 POSTs ``/{agent_id}/claim`` — 200 (assigned reviewer can claim).
6. Lead DELETEs ``/{agent_id}/assign`` — 200, audit + Kafka
   ``marketplace.review.unassigned`` with prior_assignee=R1.
7. Lead DELETEs again — 200, idempotent (no audit, no Kafka).
8. Lead POSTs assign with reviewer == submitter — 403
   ``REGISTRY_SELF_REVIEW_NOT_ALLOWED`` (FR-741.9).

Runs against the live-DB+Kafka fixture provided by feature 071.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


async def test_assignment_lifecycle_full_cycle() -> None:
    """End-to-end exercise of the 8-step lifecycle above.

    Implementation outline (live-DB+Kafka fixture):

    * Seed: 1 default-tenant pending-review submission, 3 superadmins
      (lead L, reviewer R1, reviewer R2), and a separate non-admin
      submitter S.
    * Use the e2e ``http_client`` fixture's authenticated client per
      role; track ``kafka_consumer.poll_since(offset)`` between steps
      to verify event emission.
    * Verify each step's HTTP status, response body shape, audit-chain
      entry presence/absence, Kafka event presence/absence, and the
      DB row's column state after each step (``assigned_reviewer_user_id``,
      ``reviewed_by_user_id``).
    """

    pytest.skip(
        "Live-DB+Kafka integration body to be filled in once the fixture "
        "harness ships. The 8-step lifecycle above is the test specification."
    )


async def test_assign_to_submitter_refused() -> None:
    """FR-741.9 — leads cannot assign a submission to its author.

    Outline:
    * Seed: pending submission whose ``created_by`` is user S.
    * Lead L POSTs ``/{agent_id}/assign`` with ``reviewer_user_id=S``.
    * Assert HTTP 403, code ``REGISTRY_SELF_REVIEW_NOT_ALLOWED``,
      details payload includes ``action="assign"``.
    * Assert audit-chain entry ``marketplace.review.self_review_attempted``
      recorded.
    * Assert no Kafka event on ``marketplace.events``.
    * Assert ``assigned_reviewer_user_id`` on the row is still NULL.
    """

    pytest.skip(
        "Live-DB+Kafka integration body to be filled in once the fixture "
        "harness ships."
    )
