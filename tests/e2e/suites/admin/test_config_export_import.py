from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def test_config_import_export_ui_calls_signed_bundle_endpoints() -> None:
    installer = (ROOT / "apps/web/app/(admin)/admin/lifecycle/installer/page.tsx").read_text()

    assert "/api/v1/admin/config/export" in installer
    assert "/api/v1/admin/config/import/preview" in installer
    assert "/api/v1/admin/config/import/apply" in installer
    assert "IMPORT CONFIG" in installer
    assert "Secrets omitted from bundles" in installer


@pytest.mark.asyncio
async def test_corrupted_config_import_bundle_is_rejected(http_client_superadmin) -> None:
    files = {"bundle": ("corrupt.tar.gz", b"not-a-valid-signed-bundle", "application/gzip")}
    response = await http_client_superadmin.post("/api/v1/admin/config/import/preview", files=files)
    assert response.status_code in {400, 422}
