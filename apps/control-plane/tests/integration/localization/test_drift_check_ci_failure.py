from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from platform.localization.tooling import drift_check

import pytest

pytestmark = pytest.mark.integration


def test_drift_check_cli_returns_failure_for_over_threshold_namespace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    response = drift_check.evaluate_drift(
        {
            "en": {"marketplace": now},
            "es": {"marketplace": now - timedelta(days=8)},
        },
        {"marketplace"},
        now=now,
    )
    logged: list[dict[str, object]] = []

    async def fake_run_drift_check(*, pr_base: str, repo_root: Path):
        assert pr_base == "base-sha"
        assert repo_root == tmp_path
        return response

    class Logger:
        def error(self, event: str, **payload: object) -> None:
            logged.append({"event": event, **payload})

        def info(self, event: str, **payload: object) -> None:
            logged.append({"event": event, **payload})

    monkeypatch.setattr(drift_check, "run_drift_check", fake_run_drift_check)
    monkeypatch.setattr(drift_check, "LOG", Logger())

    status = drift_check.main(["--pr-base", "base-sha", "--repo-root", str(tmp_path)])

    assert status == 1
    assert logged[0]["event"] == "localization_translation_drift_detected"
    over_threshold = logged[0]["over_threshold"]
    assert isinstance(over_threshold, list)
    assert over_threshold[0]["locale_code"] == "es"
    assert over_threshold[0]["namespace"] == "marketplace"
