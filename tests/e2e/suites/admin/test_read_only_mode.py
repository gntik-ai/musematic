from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def test_admin_write_buttons_expose_read_only_tooltip() -> None:
    write_button = (
        ROOT / "apps/web/components/features/admin/AdminWriteButton.tsx"
    ).read_text()
    table = (ROOT / "apps/web/components/features/admin/BulkActionBar.tsx").read_text()

    assert "Disabled - this session is in read-only mode" in write_button
    assert "useAdminStore" in write_button
    assert "AdminWriteButton" in table


@pytest.mark.asyncio
async def test_read_only_mode_blocks_admin_write_api(http_client) -> None:
    toggle = await http_client.patch(
        "/api/v1/admin/sessions/me/read-only-mode",
        json={"enabled": True},
    )
    assert toggle.status_code in {200, 204}

    response = await http_client.post("/api/v1/admin/users/123/suspend")
    assert response.status_code == 403
    assert "admin_read_only_mode" in response.text
