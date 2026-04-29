from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from platform.common import database
from platform.localization.constants import DEFAULT_LOCALE, DRIFT_THRESHOLD_DAYS, LOCALES
from platform.localization.repository import LocalizationRepository
from platform.localization.schemas import DriftCheckNamespaceRow, DriftCheckResponse

import structlog

LOG = structlog.get_logger(__name__)
MESSAGES_ROOT = Path("apps/web/messages")


def evaluate_drift(
    namespace_timestamps: Mapping[str, Mapping[str, datetime]],
    touched_namespaces: Iterable[str],
    *,
    threshold_days: int = DRIFT_THRESHOLD_DAYS,
    locales: Sequence[str] = LOCALES,
    default_locale: str = DEFAULT_LOCALE,
    now: datetime | None = None,
) -> DriftCheckResponse:
    reference_now = now or datetime.now(UTC)
    english_timestamps = namespace_timestamps.get(default_locale, {})
    rows: list[DriftCheckNamespaceRow] = []

    for namespace in sorted({item for item in touched_namespaces if item}):
        english_published_at = english_timestamps.get(namespace)
        for locale_code in locales:
            if locale_code == default_locale:
                continue

            localized_published_at = namespace_timestamps.get(locale_code, {}).get(namespace)
            days_drift = _calculate_days_drift(
                english_published_at,
                localized_published_at,
                reference_now,
            )
            missing_localization = (
                localized_published_at is None and english_published_at is not None
            )
            over_threshold = days_drift is not None and days_drift > threshold_days
            rows.append(
                DriftCheckNamespaceRow(
                    namespace=namespace,
                    locale_code=locale_code,
                    english_published_at=english_published_at,
                    localized_published_at=localized_published_at,
                    days_drift=days_drift,
                    in_grace=missing_localization and not over_threshold,
                    over_threshold=over_threshold,
                )
            )

    return DriftCheckResponse(threshold_days=threshold_days, rows=rows)


def collect_touched_namespaces(
    changed_paths: Iterable[str],
    *,
    repo_root: Path,
) -> set[str]:
    namespaces: set[str] = set()
    for raw_path in changed_paths:
        path = Path(raw_path)
        if path.suffix != ".json" or MESSAGES_ROOT not in path.parents:
            continue

        catalogue_path = repo_root / path
        if not catalogue_path.exists():
            continue

        try:
            payload = json.loads(catalogue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            namespaces.add(path.stem)
            continue

        if isinstance(payload, dict):
            namespaces.update(str(key) for key in payload if key)
        else:
            namespaces.add(path.stem)

    return namespaces


def get_changed_message_paths(pr_base: str, *, repo_root: Path) -> list[str]:
    completed = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            pr_base,
            "HEAD",
            "--",
            str(MESSAGES_ROOT),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


async def run_drift_check(
    *,
    pr_base: str,
    repo_root: Path,
) -> DriftCheckResponse:
    changed_paths = get_changed_message_paths(pr_base, repo_root=repo_root)
    touched_namespaces = collect_touched_namespaces(changed_paths, repo_root=repo_root)
    async with database.AsyncSessionLocal() as session:
        repository = LocalizationRepository(session)
        timestamps = await repository.get_namespace_publish_timestamps_per_locale()
    return evaluate_drift(timestamps, touched_namespaces)


def emit_result(response: DriftCheckResponse) -> None:
    over_threshold = [row for row in response.rows if row.over_threshold]
    payload = {
        "threshold_days": response.threshold_days,
        "over_threshold": [row.model_dump(mode="json") for row in over_threshold],
        "rows": [row.model_dump(mode="json") for row in response.rows],
    }
    if over_threshold:
        LOG.error("localization_translation_drift_detected", **payload)
    else:
        LOG.info("localization_translation_drift_ok", **payload)


async def async_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check translation drift by namespace.")
    parser.add_argument("--pr-base", required=True, help="Base SHA to compare against HEAD.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root. Defaults to the current working directory.",
    )
    args = parser.parse_args(argv)

    response = await run_drift_check(pr_base=args.pr_base, repo_root=args.repo_root)
    emit_result(response)
    return 1 if any(row.over_threshold for row in response.rows) else 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


def _calculate_days_drift(
    english_published_at: datetime | None,
    localized_published_at: datetime | None,
    now: datetime,
) -> float | None:
    if english_published_at is None:
        return None
    if localized_published_at is None:
        return _days_between(now, english_published_at)
    if english_published_at <= localized_published_at:
        return 0.0
    return _days_between(english_published_at, localized_published_at)


def _days_between(left: datetime, right: datetime) -> float:
    return (left - right).total_seconds() / 86_400


if __name__ == "__main__":
    raise SystemExit(main())
