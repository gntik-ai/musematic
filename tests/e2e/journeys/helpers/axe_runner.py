from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_allowlist(path: Path) -> dict[str, list[dict[str, str]]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    pages = payload.get("pages", {})
    return pages if isinstance(pages, dict) else {}


def _allowlisted(
    *,
    page_url: str,
    rule_id: str,
    allowlist: dict[str, list[dict[str, str]]],
) -> bool:
    for pattern, entries in allowlist.items():
        if not re.search(pattern, page_url):
            continue
        for entry in entries:
            if entry.get("rule_id") == rule_id:
                logger.info(
                    "Filtered allowlisted axe violation",
                    extra={
                        "rule_id": rule_id,
                        "page_url": page_url,
                        "justification": entry.get("justification"),
                        "tracking_id": entry.get("tracking_id"),
                        "expiry_date": entry.get("expiry_date"),
                    },
                )
                return True
    return False


async def _run_axe(page: Any) -> dict[str, Any]:
    try:
        from axe_playwright_python.async_playwright import Axe
    except ImportError:
        try:
            from axe_playwright_python import Axe
        except ImportError as exc:
            raise RuntimeError(
                "axe-playwright-python is required for accessibility scans"
            ) from exc

    axe = Axe()
    return await axe.run(page)


async def run_axe_scan(
    page: Any,
    allowlist_path: Path,
    impact: str = "moderate",
) -> list[dict]:
    result = await _run_axe(page)
    page_url = str(getattr(page, "url", ""))
    allowlist = _load_allowlist(allowlist_path)
    impacts = {"minor": 0, "moderate": 1, "serious": 2, "critical": 3}
    minimum = impacts.get(impact, impacts["moderate"])
    remaining: list[dict] = []

    for violation in result.get("violations", []):
        rule_id = str(violation.get("id") or violation.get("rule_id") or "")
        violation_impact = str(violation.get("impact") or "minor")
        if impacts.get(violation_impact, 0) < minimum:
            continue
        if _allowlisted(page_url=page_url, rule_id=rule_id, allowlist=allowlist):
            continue
        normalized = dict(violation)
        normalized["rule_id"] = rule_id
        remaining.append(normalized)
    return remaining
