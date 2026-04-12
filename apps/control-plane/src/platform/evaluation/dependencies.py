from __future__ import annotations

from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.evaluation.ab_experiment_service import AbExperimentService
from platform.evaluation.ate_service import ATEService
from platform.evaluation.human_grading_service import HumanGradingService
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.robustness_service import RobustnessTestService
from platform.evaluation.scorers.llm_judge import LLMJudgeScorer
from platform.evaluation.scorers.registry import ScorerRegistry
from platform.evaluation.scorers.semantic import SemanticSimilarityScorer
from platform.evaluation.scorers.trajectory import TrajectoryScorer
from platform.evaluation.service import EvalRunnerService, EvalSuiteService
from platform.execution.dependencies import build_execution_service
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_qdrant(request: Request) -> AsyncQdrantClient:
    return cast(AsyncQdrantClient, request.app.state.clients["qdrant"])


def _get_runtime_controller(request: Request) -> RuntimeControllerClient | None:
    return cast(RuntimeControllerClient | None, request.app.state.clients.get("runtime_controller"))


def _get_reasoning_engine(request: Request) -> ReasoningEngineClient | None:
    return cast(ReasoningEngineClient | None, request.app.state.clients.get("reasoning_engine"))


def _get_object_storage(request: Request) -> AsyncObjectStorageClient:
    return cast(AsyncObjectStorageClient, request.app.state.clients["minio"])


def build_scorer_registry(
    *,
    settings: PlatformSettings,
    qdrant: AsyncQdrantClient,
    execution_service: Any | None,
    reasoning_engine: Any | None,
) -> ScorerRegistry:
    registry = ScorerRegistry()
    from platform.evaluation.scorers.exact_match import ExactMatchScorer
    from platform.evaluation.scorers.json_schema import JsonSchemaScorer
    from platform.evaluation.scorers.regex import RegexScorer

    registry.register("exact_match", ExactMatchScorer())
    registry.register("regex", RegexScorer())
    registry.register("json_schema", JsonSchemaScorer())
    registry.register(
        "semantic",
        SemanticSimilarityScorer(settings=settings, qdrant=qdrant),
    )
    llm_judge = LLMJudgeScorer(settings=settings)
    registry.register("llm_judge", llm_judge)
    registry.register(
        "trajectory",
        TrajectoryScorer(
            execution_query=execution_service,
            reasoning_engine=reasoning_engine,
            llm_judge=llm_judge,
        ),
    )
    return registry


def build_eval_suite_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
) -> EvalSuiteService:
    return EvalSuiteService(
        repository=EvaluationRepository(session),
        settings=settings,
        producer=producer,
    )


async def get_eval_suite_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> EvalSuiteService:
    return build_eval_suite_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
    )


def build_eval_runner_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    qdrant: AsyncQdrantClient,
    runtime_controller: RuntimeControllerClient | Any | None,
    reasoning_engine: ReasoningEngineClient | Any | None,
    execution_service: Any | None,
    drift_service: Any | None = None,
) -> EvalRunnerService:
    return EvalRunnerService(
        repository=EvaluationRepository(session),
        settings=settings,
        scorer_registry=build_scorer_registry(
            settings=settings,
            qdrant=qdrant,
            execution_service=execution_service,
            reasoning_engine=reasoning_engine,
        ),
        producer=producer,
        runtime_controller=runtime_controller,
        execution_query=execution_service,
        drift_service=drift_service,
    )


async def get_eval_runner_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> EvalRunnerService:
    execution_service = build_execution_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=cast(Any, request.app.state.clients["redis"]),
        object_storage=_get_object_storage(request),
        runtime_controller=_get_runtime_controller(request),
        reasoning_engine=_get_reasoning_engine(request),
        context_engineering_service=getattr(request.app.state, "context_engineering_service", None),
    )
    return build_eval_runner_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        qdrant=_get_qdrant(request),
        runtime_controller=_get_runtime_controller(request),
        reasoning_engine=_get_reasoning_engine(request),
        execution_service=execution_service,
    )


def build_ab_experiment_service(
    *,
    session: AsyncSession,
    producer: EventProducer | None,
) -> AbExperimentService:
    return AbExperimentService(
        repository=EvaluationRepository(session),
        producer=producer,
    )


async def get_ab_experiment_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AbExperimentService:
    return build_ab_experiment_service(session=session, producer=_get_producer(request))


def build_ate_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    object_storage: AsyncObjectStorageClient,
    simulation_controller: Any | None,
    eval_runner_service: EvalRunnerService,
) -> ATEService:
    return ATEService(
        repository=EvaluationRepository(session),
        settings=settings,
        producer=producer,
        object_storage=object_storage,
        simulation_controller=simulation_controller,
        eval_runner_service=eval_runner_service,
    )


async def get_ate_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    eval_runner_service: EvalRunnerService = Depends(get_eval_runner_service),
) -> ATEService:
    return build_ate_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        object_storage=_get_object_storage(request),
        simulation_controller=cast(Any, request.app.state.clients.get("simulation_controller")),
        eval_runner_service=eval_runner_service,
    )


def build_robustness_service(
    *,
    session: AsyncSession,
    eval_runner_service: EvalRunnerService,
    producer: EventProducer | None,
) -> RobustnessTestService:
    return RobustnessTestService(
        repository=EvaluationRepository(session),
        eval_runner_service=eval_runner_service,
        producer=producer,
    )


async def get_robustness_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    eval_runner_service: EvalRunnerService = Depends(get_eval_runner_service),
) -> RobustnessTestService:
    return build_robustness_service(
        session=session,
        eval_runner_service=eval_runner_service,
        producer=_get_producer(request),
    )


def build_human_grading_service(
    *,
    session: AsyncSession,
    producer: EventProducer | None,
) -> HumanGradingService:
    return HumanGradingService(
        repository=EvaluationRepository(session),
        producer=producer,
    )


async def get_human_grading_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> HumanGradingService:
    return build_human_grading_service(session=session, producer=_get_producer(request))
