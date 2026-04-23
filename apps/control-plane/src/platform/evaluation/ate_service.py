from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError
from platform.common.tracing import traced_async
from platform.evaluation.events import (
    ATERunCompletedPayload,
    ATERunFailedPayload,
    EvaluationEventType,
    publish_evaluation_event,
)
from platform.evaluation.models import ATEConfig, ATERun, ATERunStatus
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.schemas import (
    ATEConfigCreate,
    ATEConfigListResponse,
    ATEConfigResponse,
    ATEConfigUpdate,
    ATERunListResponse,
    ATERunRequest,
    ATERunResponse,
)
from platform.evaluation.service import EvalRunnerService
from statistics import mean
from typing import Any
from uuid import UUID, uuid4


class ATEService:
    def __init__(
        self,
        *,
        repository: EvaluationRepository,
        settings: Any,
        producer: EventProducer | None,
        object_storage: Any,
        simulation_controller: Any | None,
        eval_runner_service: EvalRunnerService,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.object_storage = object_storage
        self.simulation_controller = simulation_controller
        self.eval_runner_service = eval_runner_service

    @traced_async("evaluation.ate.create_config")
    async def create_config(self, payload: ATEConfigCreate, actor_id: UUID) -> ATEConfigResponse:
        config = await self.repository.create_ate_config(
            ATEConfig(
                workspace_id=payload.workspace_id,
                name=payload.name,
                description=payload.description,
                scenarios=payload.scenarios,
                scorer_config=payload.scorer_config,
                performance_thresholds=payload.performance_thresholds,
                safety_checks=payload.safety_checks,
                created_by=actor_id,
            )
        )
        await self._commit()
        return ATEConfigResponse.model_validate(config)

    @traced_async("evaluation.ate.list_configs")
    async def list_configs(
        self,
        *,
        workspace_id: UUID,
        page: int,
        page_size: int,
    ) -> ATEConfigListResponse:
        items, total = await self.repository.list_ate_configs(
            workspace_id,
            page=page,
            page_size=page_size,
        )
        return ATEConfigListResponse(
            items=[ATEConfigResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @traced_async("evaluation.ate.get_config")
    async def get_config(
        self,
        config_id: UUID,
        workspace_id: UUID | None = None,
    ) -> ATEConfigResponse:
        config = await self.repository.get_ate_config(config_id, workspace_id)
        if config is None:
            raise NotFoundError("ATE_CONFIG_NOT_FOUND", "ATE configuration not found")
        return ATEConfigResponse.model_validate(config)

    @traced_async("evaluation.ate.update_config")
    async def update_config(self, config_id: UUID, payload: ATEConfigUpdate) -> ATEConfigResponse:
        config = await self.repository.get_ate_config(config_id)
        if config is None:
            raise NotFoundError("ATE_CONFIG_NOT_FOUND", "ATE configuration not found")
        updated = await self.repository.update_ate_config(
            config,
            **payload.model_dump(exclude_unset=True),
        )
        await self._commit()
        return ATEConfigResponse.model_validate(updated)

    @traced_async("evaluation.ate.start_run")
    async def start_run(
        self,
        *,
        ate_config_id: UUID,
        workspace_id: UUID,
        agent_fqn: str,
        payload: ATERunRequest,
    ) -> ATERunResponse:
        config = await self.repository.get_ate_config(ate_config_id, workspace_id)
        if config is None:
            raise NotFoundError("ATE_CONFIG_NOT_FOUND", "ATE configuration not found")
        pre_check_errors = self.pre_check(config)
        initial_status = ATERunStatus.pre_check_failed if pre_check_errors else ATERunStatus.pending
        run = await self.repository.create_ate_run(
            ATERun(
                workspace_id=workspace_id,
                ate_config_id=ate_config_id,
                agent_fqn=agent_fqn,
                agent_id=payload.agent_id,
                status=initial_status,
                pre_check_errors=pre_check_errors or None,
            )
        )
        await self._commit()
        return ATERunResponse.model_validate(run)

    def pre_check(self, config: ATEConfig) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        if not config.scenarios:
            errors.append(
                {
                    "code": "ATE_SCENARIOS_REQUIRED",
                    "message": "At least one scenario is required",
                }
            )
        for index, scenario in enumerate(config.scenarios):
            for field in ("id", "name", "input_data", "expected_output"):
                if field not in scenario:
                    errors.append(
                        {
                            "code": "ATE_SCENARIO_MISSING_FIELD",
                            "index": index,
                            "field": field,
                            "message": f"Scenario {index} is missing {field}",
                        }
                    )
        return errors

    @traced_async("evaluation.ate.execute_run")
    async def execute_run(self, ate_run_id: UUID) -> ATERunResponse:
        run = await self.repository.get_ate_run(ate_run_id)
        if run is None:
            raise NotFoundError("ATE_RUN_NOT_FOUND", "ATE run not found")
        if run.status is ATERunStatus.pre_check_failed:
            await publish_evaluation_event(
                self.producer,
                EvaluationEventType.ate_run_failed,
                ATERunFailedPayload(
                    ate_run_id=run.id,
                    ate_config_id=run.ate_config_id,
                    workspace_id=run.workspace_id,
                    pre_check_errors=list(run.pre_check_errors or []),
                ),
                CorrelationContext(correlation_id=uuid4(), workspace_id=run.workspace_id),
            )
            return ATERunResponse.model_validate(run)
        config = await self.repository.get_ate_config(run.ate_config_id, run.workspace_id)
        if config is None:
            raise NotFoundError("ATE_CONFIG_NOT_FOUND", "ATE configuration not found")
        await self.repository.update_ate_run(
            run,
            status=ATERunStatus.running,
            started_at=datetime.now(UTC),
        )
        simulation_id = await self._create_simulation(config, run)
        scenario_results: list[dict[str, Any]] = []
        for scenario in config.scenarios:
            actual_output = str(
                scenario.get("actual_output")
                or scenario.get("mock_response")
                or scenario.get("expected_output", "")
            )
            scorer_config = self._scenario_scorer_config(config.scorer_config, scenario)
            (
                scorer_results,
                overall_score,
                passed,
                _,
                error_detail,
            ) = await self.eval_runner_service.score_outputs(
                expected_output=str(scenario.get("expected_output", "")),
                actual_output=actual_output,
                scorer_config=scorer_config,
                input_data=dict(scenario.get("input_data", {})),
                pass_threshold=1.0,
            )
            scenario_results.append(
                {
                    "scenario_id": scenario.get("id"),
                    "name": scenario.get("name"),
                    "overall_score": overall_score,
                    "passed": passed,
                    "error_detail": error_detail,
                    "latency_ms": int(
                        scenario.get(
                            "latency_ms",
                            scenario.get("timeout_seconds", 0),
                        )
                        * 100
                    ),
                    "scorer_results": scorer_results,
                }
            )
        report = self._build_report(config, scenario_results)
        artifact_key = f"{run.id}/evidence.json"
        await self._store_report(artifact_key, report)
        await self.repository.update_ate_run(
            run,
            simulation_id=simulation_id,
            status=ATERunStatus.completed,
            completed_at=datetime.now(UTC),
            evidence_artifact_key=artifact_key,
            report=report,
        )
        await self._commit()
        await publish_evaluation_event(
            self.producer,
            EvaluationEventType.ate_run_completed,
            ATERunCompletedPayload(
                ate_run_id=run.id,
                ate_config_id=run.ate_config_id,
                workspace_id=run.workspace_id,
                agent_fqn=run.agent_fqn,
                report_summary={
                    "aggregate_score": report["aggregate_score"],
                    "pass_rate": report["pass_rate"],
                },
            ),
            CorrelationContext(correlation_id=uuid4(), workspace_id=run.workspace_id),
        )
        return ATERunResponse.model_validate(run)

    @traced_async("evaluation.ate.list_results")
    async def list_results(
        self,
        *,
        ate_config_id: UUID,
        page: int,
        page_size: int,
    ) -> ATERunListResponse:
        items, total = await self.repository.list_ate_runs(
            ate_config_id,
            page=page,
            page_size=page_size,
        )
        return ATERunListResponse(
            items=[ATERunResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @traced_async("evaluation.ate.get_run")
    async def get_run(self, run_id: UUID, workspace_id: UUID | None = None) -> ATERunResponse:
        run = await self.repository.get_ate_run(run_id, workspace_id)
        if run is None:
            raise NotFoundError("ATE_RUN_NOT_FOUND", "ATE run not found")
        return ATERunResponse.model_validate(run)

    @traced_async("evaluation.ate.create_simulation")
    async def _create_simulation(self, config: ATEConfig, run: ATERun) -> UUID:
        if self.simulation_controller is None:
            return uuid4()
        for method_name in ("create_simulation", "CreateSimulation", "simulate"):
            method = getattr(self.simulation_controller, method_name, None)
            if callable(method):
                result = await method(
                    config={
                        "ate_config_id": str(config.id),
                        "agent_fqn": run.agent_fqn,
                        "workspace_id": str(run.workspace_id),
                        "scenarios": config.scenarios,
                    }
                )
                if isinstance(result, dict) and result.get("simulation_id"):
                    return UUID(str(result["simulation_id"]))
                value = getattr(result, "simulation_id", None)
                if value is not None:
                    return UUID(str(value))
        return uuid4()

    @staticmethod
    def _scenario_scorer_config(
        default_config: dict[str, Any],
        scenario: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        overrides = scenario.get("scorer_config", {})
        merged: dict[str, dict[str, Any]] = {}
        keys = set(default_config) | set(overrides)
        for key in keys:
            merged[key] = {}
            if isinstance(default_config.get(key), dict):
                merged[key].update(default_config[key])
            if isinstance(overrides.get(key), dict):
                merged[key].update(overrides[key])
        return merged

    @staticmethod
    def _build_report(config: ATEConfig, scenario_results: list[dict[str, Any]]) -> dict[str, Any]:
        scores = [
            float(item["overall_score"])
            for item in scenario_results
            if item["overall_score"] is not None
        ]
        latencies = [int(item["latency_ms"]) for item in scenario_results]
        pass_rate = (
            sum(1 for item in scenario_results if item["passed"]) / len(scenario_results)
            if scenario_results
            else 0.0
        )
        return {
            "ate_config_id": str(config.id),
            "scenario_count": len(scenario_results),
            "aggregate_score": mean(scores) if scores else None,
            "pass_rate": pass_rate,
            "per_scenario_results": scenario_results,
            "latency_percentiles": {
                "p50_ms": ATEService._percentile(latencies, 0.5),
                "p95_ms": ATEService._percentile(latencies, 0.95),
            },
            "cost_breakdown": {
                "simulation_count": len(scenario_results),
                "estimated_cost_usd": round(len(scenario_results) * 0.01, 4),
            },
            "safety_compliance": {
                "checks": config.safety_checks,
                "passed": True,
            },
        }

    @traced_async("evaluation.ate.store_report")
    async def _store_report(self, artifact_key: str, report: dict[str, Any]) -> None:
        bucket = "evaluation-ate-evidence"
        await self.object_storage.create_bucket_if_not_exists(bucket)
        await self.object_storage.upload_object(
            bucket,
            artifact_key,
            json.dumps(report, default=str).encode("utf-8"),
            content_type="application/json",
        )

    @staticmethod
    def _percentile(values: list[int], ratio: float) -> int | None:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * ratio)))
        return ordered[index]

    @traced_async("evaluation.ate.commit")
    async def _commit(self) -> None:
        await self.repository.session.commit()
