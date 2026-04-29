from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from platform.localization.tooling.drift_check import collect_touched_namespaces, evaluate_drift

NOW = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)


def test_drift_check_flags_locale_namespace_over_threshold() -> None:
    response = evaluate_drift(
        {
            "en": {"marketplace": NOW},
            "es": {"marketplace": NOW - timedelta(days=8, hours=1)},
            "fr": {"marketplace": NOW - timedelta(days=1)},
        },
        {"marketplace"},
        now=NOW,
    )

    rows = {(row.locale_code, row.namespace): row for row in response.rows}
    assert rows[("es", "marketplace")].over_threshold is True
    assert rows[("es", "marketplace")].days_drift is not None
    assert rows[("es", "marketplace")].days_drift > 8
    assert rows[("fr", "marketplace")].over_threshold is False


def test_drift_check_threshold_boundary_is_exclusive() -> None:
    response = evaluate_drift(
        {
            "en": {"auth": NOW},
            "de": {"auth": NOW - timedelta(days=7)},
        },
        {"auth"},
        now=NOW,
    )

    german = next(row for row in response.rows if row.locale_code == "de")
    assert german.days_drift == 7.0
    assert german.over_threshold is False


def test_drift_check_marks_brand_new_missing_namespace_in_grace() -> None:
    response = evaluate_drift(
        {"en": {"preferences": NOW - timedelta(days=2)}},
        {"preferences"},
        now=NOW,
    )

    spanish = next(row for row in response.rows if row.locale_code == "es")
    assert spanish.localized_published_at is None
    assert spanish.in_grace is True
    assert spanish.over_threshold is False


def test_collect_touched_namespaces_reads_changed_catalogues(tmp_path: Path) -> None:
    messages_dir = tmp_path / "apps" / "web" / "messages"
    messages_dir.mkdir(parents=True)
    (messages_dir / "en.json").write_text(
        json.dumps({"marketplace": {"title": "Marketplace"}, "auth": {}}),
        encoding="utf-8",
    )

    namespaces = collect_touched_namespaces(
        ["apps/web/messages/en.json", "apps/web/components/Unrelated.tsx"],
        repo_root=tmp_path,
    )

    assert namespaces == {"auth", "marketplace"}
