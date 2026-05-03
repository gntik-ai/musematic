"""UPD-050 migration smoke test — verifies migration 109 declares all the
tables, seed rows, CHECK constraints, and the partial index that the
data model contract requires.

Pattern matches the existing migration smoke tests
(``test_108_marketplace_scope.py``): static source-text assertions over
the migration file. The full live-DB upgrade path lives in
``apps/control-plane/tests/integration/security/abuse_prevention/`` once the
fixture is wired.
"""

from __future__ import annotations

from pathlib import Path

MIGRATION_PATH = Path("migrations/versions/110_abuse_prevention.py")


def _source() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_109_migration_creates_six_tables() -> None:
    source = _source()
    for table in (
        "abuse_prevention_settings",
        "disposable_email_domains",
        "disposable_email_overrides",
        "trusted_source_allowlist",
        "signup_velocity_counters",
        "account_suspensions",
    ):
        assert f'"{table}"' in source or f"'{table}'" in source, (
            f"migration 109 missing table {table!r}"
        )


def test_109_migration_seeds_settings() -> None:
    source = _source()
    for key in (
        "velocity_per_ip_hour",
        "velocity_per_asn_hour",
        "velocity_per_email_domain_day",
        "captcha_enabled",
        "captcha_provider",
        "geo_block_mode",
        "geo_block_country_codes",
        "fraud_scoring_provider",
        "fraud_scoring_threshold",
        "disposable_email_blocking",
        "auto_suspension_cost_burn_multiplier",
        "auto_suspension_velocity_repeat_threshold",
    ):
        assert f'"{key}"' in source, f"migration 109 missing seed for {key!r}"


def test_109_migration_declares_check_constraints() -> None:
    source = _source()
    assert "account_suspensions_reason_check" in source
    assert "account_suspensions_suspended_by_check" in source
    assert "trusted_source_allowlist_kind_check" in source
    # Reason enum surface is encoded.
    for value in (
        "velocity_repeat",
        "fraud_score",
        "cost_burn_rate",
        "disposable_email_pattern",
        "captcha_replay",
        "geo_violation",
        "manual",
        "tenant_admin",
    ):
        assert value in source, f"migration 109 missing reason value {value!r}"


def test_109_migration_declares_partial_index() -> None:
    source = _source()
    assert "as_user_active_idx" in source
    # The partial-index predicate.
    assert "lifted_at IS NULL" in source


def test_109_migration_chains_to_108() -> None:
    source = _source()
    assert 'down_revision: str | None = "108_marketplace_scope_review"' in source
    assert 'revision: str = "110_abuse_prevention"' in source
