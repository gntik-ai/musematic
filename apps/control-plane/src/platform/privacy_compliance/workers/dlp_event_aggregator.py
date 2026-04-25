from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.privacy_compliance.repository import PrivacyComplianceRepository


class DLPEventAggregator:
    def __init__(
        self,
        repository: PrivacyComplianceRepository,
        clickhouse_client: object | None,
        retention_days: int = 90,
    ) -> None:
        self.repository = repository
        self.clickhouse = clickhouse_client
        self.retention_days = retention_days

    async def run_once(self) -> dict[str, int]:
        del self.repository
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        return {"purge_before_epoch": int(cutoff.timestamp())}

