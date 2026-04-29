from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.incident_response.schemas import IncidentSeverity, IncidentSignal
from platform.incident_response.services.incident_service import IncidentService
from platform.incident_response.trigger_interface import IncidentTriggerInterface
from platform.multi_region_ops.schemas import (
    CapacityConfidence,
    CapacityRecommendation,
    CapacitySignalResponse,
)
from typing import Any
from uuid import UUID, uuid4

RESOURCE_CLASSES = ("compute", "memory", "storage", "events", "model_tokens")


class CapacityService:
    def __init__(
        self,
        *,
        settings: PlatformSettings,
        cost_governance_service: Any | None = None,
        analytics_service: Any | None = None,
        incident_trigger: IncidentTriggerInterface | None = None,
        incident_service: IncidentService | None = None,
    ) -> None:
        self.settings = settings
        self.cost_governance_service = cost_governance_service
        self.analytics_service = analytics_service
        self.incident_trigger = incident_trigger
        self.incident_service = incident_service

    async def get_capacity_overview(
        self,
        *,
        workspace_id: UUID | None = None,
    ) -> list[CapacitySignalResponse]:
        forecast = await self._latest_cost_forecast(workspace_id)
        rollups = await self._usage_rollups(workspace_id)
        return [
            self._signal_for(
                resource_class, forecast=forecast, rollups=rollups, workspace_id=workspace_id
            )
            for resource_class in RESOURCE_CLASSES
        ]

    async def evaluate_saturation(
        self, *, workspace_id: UUID | None = None
    ) -> list[CapacitySignalResponse]:
        signals = await self.get_capacity_overview(workspace_id=workspace_id)
        for signal in signals:
            fingerprint = capacity_fingerprint(
                signal.resource_class,
                str(workspace_id or "platform"),
            )
            if signal.recommendation is not None and self.incident_trigger is not None:
                await self.incident_trigger.fire(
                    IncidentSignal(
                        condition_fingerprint=fingerprint,
                        severity=IncidentSeverity.warning,
                        alert_rule_class="capacity_saturation_projected",
                        title=f"{signal.resource_class} capacity projected near saturation",
                        description=signal.recommendation.reason,
                        runbook_scenario="region_failover",
                        correlation_context=CorrelationContext(
                            workspace_id=workspace_id,
                            correlation_id=uuid4(),
                        ),
                    )
                )
                continue
            if signal.recommendation is None and self.incident_service is not None:
                finder = getattr(
                    getattr(self.incident_service, "repository", None),
                    "find_open_incident_by_fingerprint",
                    None,
                )
                if callable(finder):
                    existing = await finder(fingerprint)
                    if existing is not None:
                        await self.incident_service.resolve(
                            existing.id,
                            resolved_at=datetime.now(UTC),
                            auto_resolved=True,
                        )
        return signals

    async def active_recommendations(
        self,
        *,
        workspace_id: UUID | None = None,
    ) -> list[CapacitySignalResponse]:
        signals = await self.get_capacity_overview(workspace_id=workspace_id)
        return [signal for signal in signals if signal.recommendation is not None]

    async def _latest_cost_forecast(self, workspace_id: UUID | None) -> Any | None:
        if workspace_id is None or self.cost_governance_service is None:
            return None
        forecast_service = getattr(self.cost_governance_service, "forecast_service", None)
        if forecast_service is not None and hasattr(forecast_service, "get_latest_forecast"):
            return await forecast_service.get_latest_forecast(workspace_id)
        if hasattr(self.cost_governance_service, "get_latest_forecast"):
            return await self.cost_governance_service.get_latest_forecast(workspace_id)
        repository = getattr(self.cost_governance_service, "repository", None)
        if repository is not None and hasattr(repository, "get_latest_forecast"):
            return await repository.get_latest_forecast(workspace_id)
        return None

    async def _usage_rollups(self, workspace_id: UUID | None) -> list[dict[str, Any]]:
        if workspace_id is None or self.analytics_service is None:
            return []
        method = getattr(self.analytics_service, "get_workspace_usage_rollups", None)
        if callable(method):
            return list(await method(workspace_id))
        repo = getattr(self.analytics_service, "repo", None)
        if repo is not None and hasattr(repo, "query_usage_rollups"):
            end = datetime.now(UTC)
            start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            try:
                rows, _total = await repo.query_usage_rollups(
                    workspace_id,
                    "day",
                    start,
                    end,
                    None,
                    None,
                    90,
                    0,
                )
                return list(rows)
            except Exception:
                return []
        return []

    def _signal_for(
        self,
        resource_class: str,
        *,
        forecast: Any | None,
        rollups: list[dict[str, Any]],
        workspace_id: UUID | None,
    ) -> CapacitySignalResponse:
        del workspace_id
        generated_at = datetime.now(UTC)
        if not rollups and forecast is None:
            return CapacitySignalResponse(
                resource_class=resource_class,
                historical_trend=[],
                projection=None,
                confidence=CapacityConfidence.insufficient_history,
                generated_at=generated_at,
            )
        forecast_cents = getattr(forecast, "forecast_cents", None)
        confidence_interval = getattr(forecast, "confidence_interval", {}) or {}
        confidence = (
            CapacityConfidence.insufficient_history
            if confidence_interval.get("status") == "insufficient_history"
            else CapacityConfidence.ok
        )
        projection = {
            "source": "cost_governance",
            "forecast_cents": str(forecast_cents) if forecast_cents is not None else None,
            "confidence_interval": confidence_interval,
        }
        threshold = self.settings.multi_region_ops.capacity_default_utilization_threshold
        saturation_horizon = {
            "threshold": threshold,
            "horizon_days": self.settings.multi_region_ops.capacity_saturation_horizon_days,
        }
        recommendation = None
        if confidence == CapacityConfidence.ok and forecast_cents is not None:
            recommendation = CapacityRecommendation(
                action="Review capacity and cost forecast",
                link="/operator?panel=capacity",
                reason=(
                    f"{resource_class} projected usage should be reviewed against "
                    f"{int(threshold * 100)}% utilization horizon."
                ),
            )
        return CapacitySignalResponse(
            resource_class=resource_class,
            historical_trend=rollups,
            projection=projection,
            saturation_horizon=saturation_horizon,
            confidence=confidence,
            recommendation=recommendation,
            generated_at=generated_at,
        )


def capacity_fingerprint(resource_class: str, scope_id: str) -> str:
    return hashlib.sha256(f"capacity:{resource_class}:{scope_id}".encode()).hexdigest()
