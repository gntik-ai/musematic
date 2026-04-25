from __future__ import annotations

from datetime import UTC, datetime
from platform.notifications.quiet_hours import in_quiet_hours
from zoneinfo import ZoneInfoNotFoundError

import pytest


def test_simple_quiet_hours_window() -> None:
    assert in_quiet_hours(
        datetime(2026, 1, 1, 13, 30, tzinfo=UTC),
        {"start": "13:00", "end": "14:00", "timezone": "UTC"},
        severity="medium",
        bypass_severity="critical",
    )


def test_midnight_crossing_window() -> None:
    qh = {"start": "22:00", "end": "08:00", "timezone": "UTC"}

    assert in_quiet_hours(
        datetime(2026, 1, 1, 23, 0, tzinfo=UTC),
        qh,
        severity="medium",
        bypass_severity="critical",
    )
    assert in_quiet_hours(
        datetime(2026, 1, 2, 7, 30, tzinfo=UTC),
        qh,
        severity="medium",
        bypass_severity="critical",
    )
    assert not in_quiet_hours(
        datetime(2026, 1, 2, 9, 0, tzinfo=UTC),
        qh,
        severity="medium",
        bypass_severity="critical",
    )


def test_dst_spring_forward_europe_madrid() -> None:
    assert in_quiet_hours(
        datetime(2026, 3, 29, 1, 30, tzinfo=UTC),
        {"start": "03:00", "end": "04:00", "timezone": "Europe/Madrid"},
        severity="medium",
        bypass_severity="critical",
    )


def test_dst_fall_back_europe_madrid() -> None:
    qh = {"start": "02:00", "end": "03:00", "timezone": "Europe/Madrid"}

    assert in_quiet_hours(
        datetime(2026, 10, 25, 0, 30, tzinfo=UTC),
        qh,
        severity="medium",
        bypass_severity="critical",
    )
    assert in_quiet_hours(
        datetime(2026, 10, 25, 1, 30, tzinfo=UTC),
        qh,
        severity="medium",
        bypass_severity="critical",
    )


def test_critical_bypass() -> None:
    assert not in_quiet_hours(
        datetime(2026, 1, 1, 23, 0, tzinfo=UTC),
        {"start": "22:00", "end": "08:00", "timezone": "UTC"},
        severity="critical",
        bypass_severity="critical",
    )


def test_non_iana_timezone_error() -> None:
    with pytest.raises(ZoneInfoNotFoundError):
        in_quiet_hours(
            datetime(2026, 1, 1, 23, 0, tzinfo=UTC),
            {"start": "22:00", "end": "08:00", "timezone": "Not/AZone"},
            severity="medium",
            bypass_severity="critical",
        )
