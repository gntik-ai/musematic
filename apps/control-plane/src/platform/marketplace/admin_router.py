"""Admin marketplace-review router (UPD-049).

Mounts under the existing `/api/v1/admin/*` composite router. Endpoints
defined here serve the platform-staff review queue per
`specs/099-marketplace-scope/contracts/admin-marketplace-review-rest.md`:

- ``GET /api/v1/admin/marketplace-review/queue`` — list pending submissions
  cross-tenant via the platform-staff session (UPD-046 BYPASSRLS pool).
- ``POST /api/v1/admin/marketplace-review/{agent_id}/claim`` — optimistic
  conditional claim per research R6.
- ``POST /api/v1/admin/marketplace-review/{agent_id}/release`` — release a
  prior claim.
- ``POST /api/v1/admin/marketplace-review/{agent_id}/approve`` — approve and
  transition the agent to ``review_status='published'``.
- ``POST /api/v1/admin/marketplace-review/{agent_id}/reject`` — reject with a
  required reason; notification delivered to the submitter via UPD-042.

Route handlers are added in UPD-049 Phase 3 (T034). This module is the
skeleton the foundational phase establishes so subsequent phases can target
it.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/marketplace-review", tags=["admin.marketplace_review"])
