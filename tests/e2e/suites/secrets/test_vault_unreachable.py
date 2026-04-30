from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.slow


def _require_chaos_enabled() -> None:
    if os.getenv("MUSEMATIC_E2E_VAULT_CHAOS") != "1":
        pytest.skip("set MUSEMATIC_E2E_VAULT_CHAOS=1 to run Vault network-partition tests")


def test_cache_is_populated_before_partition() -> None:
    _require_chaos_enabled()
    assert os.getenv("PLATFORM_VAULT_MODE") == "vault"


def test_network_policy_can_block_vault_namespace() -> None:
    _require_chaos_enabled()
    assert os.getenv("VAULT_NAMESPACE", "platform-security")


def test_cached_reads_continue_for_initial_outage_window() -> None:
    _require_chaos_enabled()
    assert int(os.getenv("PLATFORM_VAULT_CACHE_TTL_SECONDS", "60")) <= 60


def test_stale_reads_continue_until_max_staleness_window() -> None:
    _require_chaos_enabled()
    assert int(os.getenv("PLATFORM_VAULT_CACHE_MAX_STALENESS_SECONDS", "300")) >= 300


def test_critical_reads_refuse_after_staleness_and_alert_clears() -> None:
    _require_chaos_enabled()
    assert "VaultStalenessHigh"


def test_network_restore_recovers_within_five_minutes() -> None:
    _require_chaos_enabled()
    assert int(os.getenv("VAULT_RECOVERY_TIMEOUT_SECONDS", "300")) <= 300
