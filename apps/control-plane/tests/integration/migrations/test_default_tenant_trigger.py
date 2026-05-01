from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


def test_default_tenant_immutable_trigger_is_in_migration() -> None:
    migration = (ROOT / "migrations/versions/096_tenant_table_and_seed.py").read_text(
        encoding="utf-8"
    )

    assert "tenants_default_immutable" in migration
    assert "Default tenant is immutable" in migration
    assert "00000000-0000-0000-0000-000000000001" in migration
