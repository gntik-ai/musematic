from __future__ import annotations

import hashlib
import os
from pathlib import Path


def current_test_nodeid() -> str:
    raw = os.environ.get("PYTEST_CURRENT_TEST", "")
    if not raw:
        return ""
    return raw.split(" ", 1)[0]


def journey_resource_prefix(journey_id: str, *, nodeid: str | None = None) -> str:
    resolved_nodeid = nodeid or current_test_nodeid() or journey_id
    digest = hashlib.sha1(resolved_nodeid.encode("utf-8")).hexdigest()[:8]
    return f"{journey_id}-test-{digest}-"


def fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures"
