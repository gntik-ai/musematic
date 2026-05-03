"""Geo-blocking via the MaxMind GeoLite2 Country DB (UPD-050 T058).

The DB is loaded at process start from the path configured by
``ABUSE_GEOLITE2_DB_PATH`` and held open as a single shared
``geoip2.database.Reader`` (it's immutable + thread-safe). The reader
is wrapped behind a small façade so the call sites stay testable.

When the DB file is missing (operators may run without GeoIP), the
reader is None and ``resolve_country`` returns None — the geo-block
guard then short-circuits as "unable to determine country" and lets
the request proceed (research R6: opt-in feature; default off).
"""

from __future__ import annotations

from pathlib import Path
from platform.common.logging import get_logger
from typing import Any

LOGGER = get_logger(__name__)

try:
    import geoip2.database  # type: ignore[import-not-found]
except Exception:  # pragma: no cover — geoip2 is a runtime dep
    geoip2 = None


class GeoLite2Reader:
    """Single-file wrapper around ``geoip2.database.Reader``."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._reader: Any = None
        path = Path(db_path)
        if not path.is_file():
            LOGGER.warning(
                "abuse.geo_block.db_missing",
                extra={"path": db_path},
            )
            return
        if geoip2 is None:
            LOGGER.warning("abuse.geo_block.geoip2_not_installed")
            return
        try:
            self._reader = geoip2.database.Reader(db_path)
        except Exception:  # pragma: no cover — startup edge case
            LOGGER.exception(
                "abuse.geo_block.reader_init_failed", extra={"path": db_path}
            )

    def resolve_country(self, ip: str | None) -> str | None:
        """Return the ISO-3166-1 alpha-2 country code, or None if unknown."""
        if not ip or self._reader is None:
            return None
        try:
            response = self._reader.country(ip)
        except Exception:
            return None
        country = response.country.iso_code
        return country.upper() if country else None

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None


def is_blocked(
    *,
    country: str | None,
    mode: str,
    blocked_country_codes: list[str] | tuple[str, ...] | set[str],
) -> bool:
    """Apply the geo-block policy to a resolved country code.

    Modes:

    - ``disabled`` — never blocks (the call sites should short-circuit
      before reaching this, but it's idempotent here too).
    - ``deny`` — blocks if country is in the list.
    - ``allow_only`` — blocks if country is NOT in the list (allowlist).
    """
    if mode == "disabled":
        return False
    if country is None:
        # If we can't resolve the country, fail open — the spec
        # explicitly opts geo-block in, and operators get to choose.
        # A deny-on-unknown stance is added as a future option.
        return False
    upper = country.upper()
    codes = {c.upper() for c in blocked_country_codes}
    if mode == "deny":
        return upper in codes
    if mode == "allow_only":
        return upper not in codes
    return False
