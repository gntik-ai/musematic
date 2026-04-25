from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "low": 0,
    "medium": 1,
    "warn": 2,
    "warning": 2,
    "high": 3,
    "critical": 4,
}


def in_quiet_hours(
    now_utc: datetime,
    qh: object,
    *,
    severity: str,
    bypass_severity: str,
) -> bool:
    if _rank(severity) >= _rank(bypass_severity):
        return False

    start_raw = _get(qh, "start")
    end_raw = _get(qh, "end")
    timezone = str(_get(qh, "timezone"))
    start = _parse_hhmm(str(start_raw))
    end = _parse_hhmm(str(end_raw))
    local = now_utc.astimezone(ZoneInfo(timezone)).time()
    if start <= end:
        return start <= local < end
    return local >= start or local < end


def _rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity.lower(), 1)


def _get(value: object, key: str) -> Any:
    if isinstance(value, dict):
        return value[key]
    return getattr(value, key)


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(hour=int(hour), minute=int(minute))
