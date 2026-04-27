from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


async def take_dashboard_snapshot(
    grafana_client: httpx.AsyncClient,
    dashboard_uid: str,
    time_range: str = "now-1h",
    width: int = 1920,
    height: int = 1080,
    output_dir: Path = Path("reports/snapshots"),
    journey_id: str = "",
    step: str = "",
) -> Path | None:
    response = await grafana_client.get(
        f"/render/d/{dashboard_uid}/",
        params={
            "from": time_range,
            "to": "now",
            "width": width,
            "height": height,
            "kiosk": "tv",
        },
    )
    if response.status_code == 404:
        logger.info(
            "Grafana renderer unavailable for dashboard snapshot",
            extra={"dashboard_uid": dashboard_uid, "journey_id": journey_id, "step": step},
        )
        return None
    response.raise_for_status()

    safe_journey = journey_id or "unknown"
    safe_step = (step or "snapshot").replace("/", "_").replace(" ", "_")
    snapshot_dir = output_dir / safe_journey
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{safe_step}-{dashboard_uid}.png"
    path.write_bytes(response.content)
    return path
