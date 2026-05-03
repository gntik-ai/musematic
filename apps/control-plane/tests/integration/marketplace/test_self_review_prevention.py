"""UPD-049 refresh (102) T028 — self-review prevention end-to-end.

Spec coverage: spec.md FR-741.9, contract `self-review-prevention.md`,
research R9.

Asserts for each of the four review-action endpoints:

* The API returns 403 with code ``REGISTRY_SELF_REVIEW_NOT_ALLOWED``.
* The audit-chain entry ``marketplace.review.self_review_attempted``
  is recorded with both ``submitter_user_id`` and ``actor_user_id``.
* No Kafka event is emitted on ``marketplace.events`` for the refused
  action.
* The row's state is unchanged (``review_status`` still
  ``pending_review``, ``reviewed_by_user_id`` unchanged,
  ``assigned_reviewer_user_id`` unchanged).

Runs against the live-DB+Kafka fixture provided by feature 071. The
``integration_live`` mark is selected by the orchestrator's
``make integration-test`` target.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


@pytest.mark.parametrize(
    "endpoint,body",
    [
        (
            "/api/v1/admin/marketplace-review/{agent_id}/assign",
            {"reviewer_user_id": "{actor_user_id}"},
        ),
        ("/api/v1/admin/marketplace-review/{agent_id}/claim", None),
        ("/api/v1/admin/marketplace-review/{agent_id}/approve", {"notes": None}),
        (
            "/api/v1/admin/marketplace-review/{agent_id}/reject",
            {"reason": "self-review attempt — should never land"},
        ),
    ],
)
async def test_self_review_refused_with_403(endpoint: str, body: dict | None) -> None:
    """For each of the 4 review-action routes, verify the actor==submitter
    case returns 403 ``self_review_not_allowed`` and leaves all state
    untouched. See module docstring for the full contract.

    Implementation outline (live-DB+Kafka fixture):

    1. Seed a default-tenant superadmin user who is ALSO a creator with
       a published-pending agent (one row in ``registry_agent_profiles``
       with ``review_status='pending_review'``, ``created_by=actor_user_id``).
    2. Capture the current Kafka offset on ``marketplace.events``.
    3. POST/DELETE the endpoint as that superadmin user.
    4. Assert the HTTP response: status 403, code
       ``REGISTRY_SELF_REVIEW_NOT_ALLOWED``, details payload contains
       ``submitter_user_id``, ``actor_user_id``, ``action``.
    5. Assert no new Kafka events on ``marketplace.events`` since the
       captured offset.
    6. Assert the audit-chain log contains a
       ``marketplace.review.self_review_attempted`` entry with both
       user IDs and the action verb.
    7. Assert the row's ``review_status``, ``reviewed_by_user_id``, and
       ``assigned_reviewer_user_id`` are exactly as before the call.
    """

    pytest.skip(
        "Live-DB+Kafka integration body to be filled in once the fixture "
        "harness ships under `make integration-test`. The contract above "
        "is the test specification."
    )
