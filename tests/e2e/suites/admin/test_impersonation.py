from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def test_impersonation_ui_has_superadmin_action_and_banner() -> None:
    users_page = (ROOT / "apps/web/app/(admin)/admin/users/page.tsx").read_text()
    layout = (ROOT / "apps/web/components/features/admin/AdminLayout.tsx").read_text()

    assert "Impersonate" in users_page
    assert "FEATURE_IMPERSONATION_ENABLED" in users_page
    assert "ImpersonationBanner" in layout


@pytest.mark.asyncio
async def test_impersonation_rejects_short_justification(http_client_superadmin) -> None:
    response = await http_client_superadmin.post(
        "/api/v1/admin/impersonation/start",
        json={"target_user_id": "11111111-1111-4111-8111-111111111111", "justification": "too short"},
    )
    assert response.status_code in {400, 422}
