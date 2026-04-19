from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError
from platform.context_engineering.adapters import ContextFetchRequest, ContextSourceAdapter
from platform.context_engineering.compactor import ContextCompactor
from platform.context_engineering.correlation_scheduler import CorrelationRecomputerTask
from platform.context_engineering.correlation_service import CorrelationService
from platform.context_engineering.events import (
    AssemblyCompletedPayload,
    BudgetExceededMinimumPayload,
    DriftDetectedPayload,
    publish_assembly_completed,
    publish_budget_exceeded_minimum,
    publish_drift_detected,
)
from platform.context_engineering.exceptions import (
    AbTestNotFoundError,
    BudgetExceededMinimumError,
    InvalidProfileAssignmentError,
    ProfileConflictError,
    ProfileInUseError,
    ProfileNotFoundError,
    WorkspaceAuthorizationError,
)
from platform.context_engineering.models import (
    AbTestStatus,
    CompactionStrategyType,
    ContextAbTest,
    ContextDriftAlert,
    ContextEngineeringProfile,
    ContextProfileAssignment,
    ContextSourceType,
    ProfileAssignmentLevel,
)
from platform.context_engineering.privacy_filter import PrivacyFilter
from platform.context_engineering.quality_scorer import QualityScorer
from platform.context_engineering.repository import ContextEngineeringRepository
from platform.context_engineering.schemas import (
    AbTestCreate,
    AbTestListResponse,
    AbTestResponse,
    AssemblyRecordListResponse,
    AssemblyRecordResponse,
    BudgetEnvelope,
    ContextBundle,
    ContextElement,
    ContextQualityScore,
    CorrelationFleetResponse,
    DriftAlertListResponse,
    DriftAlertResponse,
    ProfileAssignmentCreate,
    ProfileAssignmentListResponse,
    ProfileAssignmentResponse,
    ProfileCreate,
    ProfileListResponse,
    ProfileResponse,
    SourceConfig,
)
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

_DEFAULT_SOURCE_CONFIG: tuple[SourceConfig, ...] = (
    SourceConfig(source_type=ContextSourceType.system_instructions, priority=100, max_elements=1),
    SourceConfig(source_type=ContextSourceType.workflow_state, priority=95, max_elements=2),
    SourceConfig(source_type=ContextSourceType.tool_outputs, priority=90, max_elements=10),
    SourceConfig(source_type=ContextSourceType.conversation_history, priority=80, max_elements=20),
    SourceConfig(source_type=ContextSourceType.reasoning_traces, priority=75, max_elements=5),
    SourceConfig(source_type=ContextSourceType.long_term_memory, priority=70, max_elements=5),
    SourceConfig(source_type=ContextSourceType.workspace_goal_history, priority=65, max_elements=3),
    SourceConfig(source_type=ContextSourceType.connector_payloads, priority=60, max_elements=5),
    SourceConfig(source_type=ContextSourceType.workspace_metadata, priority=50, max_elements=2),
)


@dataclass(frozen=True, slots=True)
class ResolvedProfile:
    profile_id: UUID | None
    source_config: list[SourceConfig]
    budget_config: BudgetEnvelope
    compaction_strategies: list[CompactionStrategyType]
    quality_weights: dict[str, float]
    privacy_overrides: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AbTestSelection:
    test_id: UUID
    profile_id: UUID
    group: str


class ContextEngineeringService:
    def __init__(
        self,
        *,
        repository: ContextEngineeringRepository,
        adapters: dict[ContextSourceType, ContextSourceAdapter],
        quality_scorer: QualityScorer,
        compactor: ContextCompactor,
        privacy_filter: PrivacyFilter,
        object_storage: AsyncObjectStorageClient,
        clickhouse_client: AsyncClickHouseClient,
        settings: PlatformSettings,
        event_producer: EventProducer | None,
        workspaces_service: Any | None = None,
        registry_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.adapters = adapters
        self.quality_scorer = quality_scorer
        self.compactor = compactor
        self.privacy_filter = privacy_filter
        self.object_storage = object_storage
        self.clickhouse_client = clickhouse_client
        self.settings = settings
        self.event_producer = event_producer
        self.workspaces_service = workspaces_service
        self.registry_service = registry_service

    async def create_profile(
        self,
        workspace_id: UUID,
        payload: ProfileCreate,
        actor_id: UUID,
    ) -> ProfileResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        if payload.is_default:
            await self.repository.clear_default_profiles(workspace_id)
        try:
            profile = await self.repository.create_profile(
                workspace_id=workspace_id,
                created_by=actor_id,
                name=payload.name,
                description=payload.description,
                is_default=payload.is_default,
                source_config=[item.model_dump(mode="json") for item in payload.source_config],
                budget_config=payload.budget_config.model_dump(mode="json"),
                compaction_strategies=[item.value for item in payload.compaction_strategies],
                quality_weights=dict(payload.quality_weights),
                privacy_overrides=dict(payload.privacy_overrides),
            )
            await self._commit()
        except IntegrityError as exc:
            await self._rollback()
            raise ProfileConflictError(payload.name) from exc
        return self._profile_response(profile)

    async def get_profile(
        self, workspace_id: UUID, profile_id: UUID, actor_id: UUID
    ) -> ProfileResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self.repository.get_profile(workspace_id, profile_id)
        if profile is None:
            raise ProfileNotFoundError(profile_id)
        return self._profile_response(profile)

    async def list_profiles(self, workspace_id: UUID, actor_id: UUID) -> ProfileListResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        items = await self.repository.list_profiles(workspace_id)
        return ProfileListResponse(
            items=[self._profile_response(item) for item in items],
            total=len(items),
        )

    async def update_profile(
        self,
        workspace_id: UUID,
        profile_id: UUID,
        payload: ProfileCreate,
        actor_id: UUID,
    ) -> ProfileResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self.repository.get_profile(workspace_id, profile_id)
        if profile is None:
            raise ProfileNotFoundError(profile_id)
        if payload.is_default:
            await self.repository.clear_default_profiles(
                workspace_id, exclude_profile_id=profile_id
            )
        try:
            updated = await self.repository.update_profile(
                profile,
                updated_by=actor_id,
                name=payload.name,
                description=payload.description,
                is_default=payload.is_default,
                source_config=[item.model_dump(mode="json") for item in payload.source_config],
                budget_config=payload.budget_config.model_dump(mode="json"),
                compaction_strategies=[item.value for item in payload.compaction_strategies],
                quality_weights=dict(payload.quality_weights),
                privacy_overrides=dict(payload.privacy_overrides),
            )
            await self._commit()
        except IntegrityError as exc:
            await self._rollback()
            raise ProfileConflictError(payload.name) from exc
        return self._profile_response(updated)

    async def delete_profile(self, workspace_id: UUID, profile_id: UUID, actor_id: UUID) -> None:
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self.repository.get_profile(workspace_id, profile_id)
        if profile is None:
            raise ProfileNotFoundError(profile_id)
        if await self.repository.profile_has_assignments(
            profile.id
        ) or await self.repository.profile_has_active_ab_tests(profile.id):
            raise ProfileInUseError(profile.id)
        await self.repository.delete_profile(profile)
        await self._commit()

    async def assign_profile(
        self,
        workspace_id: UUID,
        profile_id: UUID,
        payload: ProfileAssignmentCreate,
        actor_id: UUID,
    ) -> ProfileAssignmentResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self.repository.get_profile(workspace_id, profile_id)
        if profile is None:
            raise ProfileNotFoundError(profile_id)
        if payload.assignment_level is ProfileAssignmentLevel.agent and not payload.agent_fqn:
            raise InvalidProfileAssignmentError("agent_fqn is required for agent-level assignment")
        if payload.assignment_level is ProfileAssignmentLevel.role_type and not payload.role_type:
            raise InvalidProfileAssignmentError("role_type is required for role-type assignment")
        assignment = await self.repository.create_assignment(
            workspace_id=workspace_id,
            profile_id=profile_id,
            assignment_level=payload.assignment_level,
            agent_fqn=payload.agent_fqn,
            role_type=payload.role_type,
        )
        await self._commit()
        return self._assignment_response(assignment)

    async def list_assignments(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        *,
        profile_id: UUID | None = None,
    ) -> ProfileAssignmentListResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        items = await self.repository.list_assignments(workspace_id, profile_id=profile_id)
        return ProfileAssignmentListResponse(
            items=[self._assignment_response(item) for item in items],
            total=len(items),
        )

    async def resolve_profile(
        self,
        *,
        workspace_id: UUID,
        agent_fqn: str,
        role_type: str | None,
        explicit_profile_id: UUID | None = None,
    ) -> ResolvedProfile:
        if explicit_profile_id is not None:
            explicit = await self.repository.get_profile(workspace_id, explicit_profile_id)
            if explicit is None:
                raise ProfileNotFoundError(explicit_profile_id)
            return self._resolved_profile(explicit)

        assignment = await self.repository.get_assignment_by_agent_fqn(workspace_id, agent_fqn)
        if assignment is not None:
            profile = await self.repository.get_profile(workspace_id, assignment.profile_id)
            if profile is not None:
                return self._resolved_profile(profile)
        if role_type:
            assignment = await self.repository.get_assignment_by_role_type(workspace_id, role_type)
            if assignment is not None:
                profile = await self.repository.get_profile(workspace_id, assignment.profile_id)
                if profile is not None:
                    return self._resolved_profile(profile)
        assignment = await self.repository.get_workspace_default_assignment(workspace_id)
        if assignment is not None:
            profile = await self.repository.get_profile(workspace_id, assignment.profile_id)
            if profile is not None:
                return self._resolved_profile(profile)
        default_profile = await self.repository.get_default_profile(workspace_id)
        if default_profile is not None:
            return self._resolved_profile(default_profile)
        return ResolvedProfile(
            profile_id=None,
            source_config=list(_DEFAULT_SOURCE_CONFIG),
            budget_config=BudgetEnvelope(),
            compaction_strategies=[
                CompactionStrategyType.relevance_truncation,
                CompactionStrategyType.priority_eviction,
                CompactionStrategyType.semantic_deduplication,
            ],
            quality_weights={},
            privacy_overrides={},
        )

    async def assemble_context(
        self,
        *,
        execution_id: UUID,
        step_id: UUID,
        agent_fqn: str,
        workspace_id: UUID,
        task_brief: str = "",
        goal_id: UUID | None = None,
        role_type: str | None = None,
        profile: UUID | None = None,
        budget: BudgetEnvelope | None = None,
        correlation_id: UUID | None = None,
    ) -> ContextBundle:
        existing = await self.repository.find_assembly_record_by_execution_step(
            workspace_id,
            execution_id,
            step_id,
        )
        if existing is not None and existing.bundle_storage_key:
            cached = await self._load_bundle(existing.bundle_storage_key)
            if cached is not None:
                return cached

        resolved_profile = await self.resolve_profile(
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
            role_type=role_type,
            explicit_profile_id=profile,
        )
        effective_budget = self._merge_budget(resolved_profile.budget_config, budget)
        ab_selection = await self._resolve_ab_test_profile(
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
            execution_id=execution_id,
        )
        if ab_selection is not None:
            ab_profile = await self.repository.get_profile(workspace_id, ab_selection.profile_id)
            if ab_profile is not None:
                resolved_profile = self._resolved_profile(ab_profile)
                effective_budget = self._merge_budget(resolved_profile.budget_config, budget)

        queried: list[str] = []
        available: list[str] = []
        elements: list[ContextElement] = []
        partial_sources = False

        enabled_sources = [item for item in resolved_profile.source_config if item.enabled]
        enabled_sources = enabled_sources[: effective_budget.max_sources]
        for source_config in enabled_sources:
            if (
                source_config.source_type is ContextSourceType.workspace_goal_history
                and goal_id is None
            ):
                continue
            queried.append(source_config.source_type.value)
            adapter = self.adapters.get(source_config.source_type)
            if adapter is None:
                partial_sources = True
                continue
            try:
                fetched = await adapter.fetch(
                    ContextFetchRequest(
                        execution_id=execution_id,
                        step_id=step_id,
                        workspace_id=workspace_id,
                        agent_fqn=agent_fqn,
                        goal_id=goal_id,
                        task_brief=task_brief,
                        source_config=source_config,
                    )
                )
            except Exception:
                partial_sources = True
                continue
            if fetched:
                available.append(source_config.source_type.value)
            elements.extend(fetched)

        for element in elements:
            element.metadata["relevance_score"] = self.quality_scorer.score_element_relevance(
                element,
                task_brief,
            )

        filtered_elements, exclusions = await self.privacy_filter.filter(
            elements,
            agent_fqn,
            workspace_id,
            privacy_overrides=resolved_profile.privacy_overrides,
        )
        pre_score = await self.quality_scorer.score(
            filtered_elements,
            task_brief,
            resolved_profile.quality_weights,
        )
        token_count_pre = sum(item.token_count for item in filtered_elements)
        compacted = list(filtered_elements)
        compaction_actions: list[dict[str, Any]] = []
        compaction_applied = False
        flags: list[str] = []

        if partial_sources:
            flags.append("partial_sources")
        if token_count_pre > effective_budget.max_tokens_step:
            try:
                compacted, compaction_actions = await self.compactor.compact(
                    filtered_elements,
                    effective_budget,
                    resolved_profile.compaction_strategies,
                )
                compaction_applied = compacted != filtered_elements
            except BudgetExceededMinimumError as exc:
                compacted = self.compactor.minimum_viable_elements(filtered_elements)
                compaction_applied = True
                flags.append("budget_exceeded_minimum")
                await publish_budget_exceeded_minimum(
                    self.event_producer,
                    BudgetExceededMinimumPayload(
                        workspace_id=workspace_id,
                        execution_id=execution_id,
                        step_id=step_id,
                        agent_fqn=agent_fqn,
                        max_tokens=exc.max_tokens,
                        minimum_tokens=exc.minimum_tokens,
                    ),
                    self._correlation(
                        correlation_id,
                        workspace_id=workspace_id,
                        execution_id=execution_id,
                        goal_id=goal_id,
                    ),
                )
        post_score = await self.quality_scorer.score(
            compacted,
            task_brief,
            resolved_profile.quality_weights,
        )
        token_count_post = sum(item.token_count for item in compacted)
        if post_score.aggregate == 0:
            flags.append("zero_quality")

        assembly_id = uuid4()
        bundle = ContextBundle(
            assembly_id=assembly_id,
            execution_id=execution_id,
            step_id=step_id,
            agent_fqn=agent_fqn,
            elements=compacted,
            quality_score=post_score.aggregate,
            quality_subscores=self._subscores(post_score),
            token_count=token_count_post,
            compaction_applied=compaction_applied,
            flags=flags,
            profile_id=resolved_profile.profile_id,
            ab_test_id=ab_selection.test_id if ab_selection is not None else None,
            ab_test_group=ab_selection.group if ab_selection is not None else None,
        )
        bundle_storage_key = self._bundle_storage_key(workspace_id, execution_id, step_id)
        await self._store_bundle(bundle_storage_key, bundle)
        record = await self.repository.create_assembly_record(
            id=assembly_id,
            workspace_id=workspace_id,
            execution_id=execution_id,
            step_id=step_id,
            agent_fqn=agent_fqn,
            profile_id=resolved_profile.profile_id,
            quality_score_pre=pre_score.aggregate,
            quality_score_post=post_score.aggregate,
            token_count_pre=token_count_pre,
            token_count_post=token_count_post,
            sources_queried=queried,
            sources_available=available,
            compaction_applied=compaction_applied,
            compaction_actions=compaction_actions,
            privacy_exclusions=exclusions,
            provenance_chain=[element.provenance.model_dump(mode="json") for element in compacted],
            bundle_storage_key=bundle_storage_key,
            ab_test_id=ab_selection.test_id if ab_selection is not None else None,
            ab_test_group=ab_selection.group if ab_selection is not None else None,
            flags=flags,
        )
        await self._write_quality_score(record, post_score)
        if ab_selection is not None:
            ab_test = await self.repository.get_ab_test(workspace_id, ab_selection.test_id)
            if ab_test is not None:
                await self.repository.update_ab_test_metrics(
                    ab_test,
                    group=ab_selection.group,
                    quality_score=post_score.aggregate,
                    token_count=token_count_post,
                )
        await self._commit()
        await publish_assembly_completed(
            self.event_producer,
            AssemblyCompletedPayload(
                assembly_id=record.id,
                workspace_id=workspace_id,
                execution_id=execution_id,
                step_id=step_id,
                agent_fqn=agent_fqn,
                quality_score=post_score.aggregate,
                token_count=token_count_post,
                ab_test_id=ab_selection.test_id if ab_selection is not None else None,
                ab_test_group=ab_selection.group if ab_selection is not None else None,
                flags=flags,
                created_at=record.created_at,
            ),
            self._correlation(
                correlation_id,
                workspace_id=workspace_id,
                execution_id=execution_id,
                goal_id=goal_id,
            ),
        )
        return bundle

    async def create_ab_test(
        self,
        workspace_id: UUID,
        payload: AbTestCreate,
        actor_id: UUID,
    ) -> AbTestResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        control = await self.repository.get_profile(workspace_id, payload.control_profile_id)
        variant = await self.repository.get_profile(workspace_id, payload.variant_profile_id)
        if control is None:
            raise ProfileNotFoundError(payload.control_profile_id)
        if variant is None:
            raise ProfileNotFoundError(payload.variant_profile_id)
        ab_test = await self.repository.create_ab_test(
            workspace_id=workspace_id,
            created_by=actor_id,
            updated_by=actor_id,
            name=payload.name,
            control_profile_id=payload.control_profile_id,
            variant_profile_id=payload.variant_profile_id,
            target_agent_fqn=payload.target_agent_fqn,
            status=AbTestStatus.active,
            started_at=datetime.now(UTC),
            ended_at=None,
            control_assembly_count=0,
            variant_assembly_count=0,
            control_quality_mean=None,
            variant_quality_mean=None,
            control_token_mean=None,
            variant_token_mean=None,
        )
        await self._commit()
        return self._ab_test_response(ab_test)

    async def get_ab_test(
        self, workspace_id: UUID, test_id: UUID, actor_id: UUID
    ) -> AbTestResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        ab_test = await self.repository.get_ab_test(workspace_id, test_id)
        if ab_test is None:
            raise AbTestNotFoundError(test_id)
        return self._ab_test_response(ab_test)

    async def list_ab_tests(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        *,
        status: AbTestStatus | None,
        limit: int,
        offset: int,
    ) -> AbTestListResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        items, total = await self.repository.list_ab_tests(
            workspace_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return AbTestListResponse(
            items=[self._ab_test_response(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def end_ab_test(
        self, workspace_id: UUID, test_id: UUID, actor_id: UUID
    ) -> AbTestResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        ab_test = await self.repository.get_ab_test(workspace_id, test_id)
        if ab_test is None:
            raise AbTestNotFoundError(test_id)
        completed = await self.repository.complete_ab_test(ab_test)
        await self._commit()
        return self._ab_test_response(completed)

    async def list_assembly_records(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        *,
        agent_fqn: str | None,
        limit: int,
        offset: int,
    ) -> AssemblyRecordListResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        items, total = await self.repository.list_assembly_records(
            workspace_id,
            agent_fqn=agent_fqn,
            limit=limit,
            offset=offset,
        )
        return AssemblyRecordListResponse(
            items=[self._record_response(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_assembly_record(
        self,
        workspace_id: UUID,
        record_id: UUID,
        actor_id: UUID,
    ) -> AssemblyRecordResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        record = await self.repository.get_assembly_record(workspace_id, record_id)
        if record is None:
            raise ProfileNotFoundError(record_id)
        return self._record_response(record)

    async def list_drift_alerts(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        *,
        resolved: bool | None,
        limit: int,
        offset: int,
    ) -> DriftAlertListResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        items, total = await self.repository.list_drift_alerts(
            workspace_id,
            resolved=resolved,
            limit=limit,
            offset=offset,
        )
        return DriftAlertListResponse(
            items=[self._alert_response(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_latest_correlation(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        *,
        agent_fqn: str,
        window_days: int | None = None,
        classification: str | None = None,
    ) -> CorrelationFleetResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        response = await self._correlation_service().get_latest(
            workspace_id,
            agent_fqn,
            window_days=window_days,
            classification=classification,
        )
        if response.total == 0:
            raise NotFoundError(
                "CONTEXT_ENGINEERING_CORRELATION_NOT_FOUND",
                "Correlation results not found",
            )
        return response

    async def query_fleet_correlations(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        *,
        classification: str | None = None,
    ) -> CorrelationFleetResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        return await self._correlation_service().query_fleet(
            workspace_id,
            classification=classification,
        )

    async def enqueue_correlation_recompute(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        *,
        agent_fqn: str | None = None,
        window_days: int | None = None,
    ) -> dict[str, object]:
        await self._assert_workspace_access(workspace_id, actor_id)
        await self._correlation_recomputer().enqueue_recompute(
            workspace_id,
            agent_fqn=agent_fqn,
            window_days=window_days,
        )
        return {"enqueued": True, "estimated_completion_seconds": 30}

    async def run_correlation_recompute(
        self,
        *,
        workspace_id: UUID | None = None,
    ) -> list[dict[str, object]]:
        return await self._correlation_recomputer().run(workspace_id)

    async def run_drift_analysis(self) -> int:
        rows = await self.clickhouse_client.execute_query(
            """
            SELECT
                workspace_id,
                agent_fqn,
                avgIf(
                    quality_score,
                    created_at >= now() - INTERVAL %(window_days)s DAY
                    AND created_at < now() - INTERVAL %(recent_hours)s HOUR
                ) AS historical_mean,
                stddevPopIf(
                    quality_score,
                    created_at >= now() - INTERVAL %(window_days)s DAY
                    AND created_at < now() - INTERVAL %(recent_hours)s HOUR
                ) AS historical_stddev,
                avgIf(
                    quality_score,
                    created_at >= now() - INTERVAL %(recent_hours)s HOUR
                ) AS recent_mean
            FROM context_quality_scores
            GROUP BY workspace_id, agent_fqn
            """,
            {
                "window_days": self.settings.context_engineering.drift_window_days,
                "recent_hours": self.settings.context_engineering.drift_recent_hours,
            },
        )
        created = 0
        for row in rows:
            historical_mean = float(row.get("historical_mean") or 0.0)
            historical_stddev = float(row.get("historical_stddev") or 0.0)
            recent_mean = float(row.get("recent_mean") or 0.0)
            if historical_mean <= 0 or historical_stddev <= 0:
                continue
            threshold = historical_mean - (
                self.settings.context_engineering.drift_stddev_multiplier * historical_stddev
            )
            if recent_mean >= threshold:
                continue
            workspace_id = UUID(str(row["workspace_id"]))
            agent_fqn = str(row["agent_fqn"])
            if await self.repository.find_unresolved_drift_alert(workspace_id, agent_fqn):
                continue
            alert = await self.repository.create_drift_alert(
                workspace_id=workspace_id,
                agent_fqn=agent_fqn,
                historical_mean=historical_mean,
                historical_stddev=historical_stddev,
                recent_mean=recent_mean,
                degradation_delta=historical_mean - recent_mean,
                analysis_window_days=self.settings.context_engineering.drift_window_days,
                suggested_actions=[
                    "Review source availability and privacy exclusions",
                    "Inspect profile budget and compaction strategies",
                    "Compare control versus variant quality trends",
                ],
            )
            await self._commit()
            created += 1
            await publish_drift_detected(
                self.event_producer,
                DriftDetectedPayload(
                    alert_id=alert.id,
                    workspace_id=workspace_id,
                    agent_fqn=agent_fqn,
                    historical_mean=historical_mean,
                    historical_stddev=historical_stddev,
                    recent_mean=recent_mean,
                    degradation_delta=historical_mean - recent_mean,
                ),
                self._correlation(None, workspace_id=workspace_id),
            )
        return created

    async def _resolve_ab_test_profile(
        self,
        *,
        workspace_id: UUID,
        agent_fqn: str,
        execution_id: UUID,
    ) -> AbTestSelection | None:
        ab_test = await self.repository.get_active_ab_test(workspace_id, agent_fqn)
        if ab_test is None:
            return None
        digest = hashlib.sha256(f"{ab_test.id}:{execution_id}".encode()).hexdigest()
        group = "variant" if int(digest[-8:], 16) % 2 else "control"
        profile_id = (
            ab_test.variant_profile_id if group == "variant" else ab_test.control_profile_id
        )
        return AbTestSelection(test_id=ab_test.id, profile_id=profile_id, group=group)

    def _correlation_service(self) -> CorrelationService:
        return CorrelationService(
            repository=self.repository,
            event_producer=self.event_producer,
            min_data_points=self.settings.context_engineering.correlation_min_data_points,
        )

    def _correlation_recomputer(self) -> CorrelationRecomputerTask:
        return CorrelationRecomputerTask(
            correlation_service=self._correlation_service(),
            registry_service=self.registry_service,
            default_window_days=self.settings.context_engineering.correlation_window_days,
        )

    def _resolved_profile(self, profile: ContextEngineeringProfile) -> ResolvedProfile:
        source_config = [SourceConfig.model_validate(item) for item in profile.source_config]
        if not source_config:
            source_config = list(_DEFAULT_SOURCE_CONFIG)
        strategies = [CompactionStrategyType(item) for item in profile.compaction_strategies] or [
            CompactionStrategyType.relevance_truncation,
            CompactionStrategyType.priority_eviction,
            CompactionStrategyType.semantic_deduplication,
        ]
        return ResolvedProfile(
            profile_id=profile.id,
            source_config=source_config,
            budget_config=BudgetEnvelope.model_validate(profile.budget_config or {}),
            compaction_strategies=strategies,
            quality_weights=dict(profile.quality_weights or {}),
            privacy_overrides=dict(profile.privacy_overrides or {}),
        )

    def _merge_budget(
        self,
        base: BudgetEnvelope,
        override: BudgetEnvelope | None,
    ) -> BudgetEnvelope:
        if override is None:
            return base
        return base.model_copy(update=override.model_dump(exclude_unset=True))

    async def _store_bundle(self, key: str, bundle: ContextBundle) -> None:
        await self.object_storage.create_bucket_if_not_exists(
            self.settings.CONTEXT_ENGINEERING_BUNDLE_BUCKET
        )
        await self.object_storage.upload_object(
            self.settings.CONTEXT_ENGINEERING_BUNDLE_BUCKET,
            key,
            bundle.model_dump_json().encode("utf-8"),
            content_type="application/json",
        )

    async def _load_bundle(self, key: str) -> ContextBundle | None:
        try:
            payload = await self.object_storage.download_object(
                self.settings.CONTEXT_ENGINEERING_BUNDLE_BUCKET,
                key,
            )
        except Exception:
            return None
        return ContextBundle.model_validate_json(payload)

    async def _write_quality_score(
        self,
        record: Any,
        score: ContextQualityScore,
    ) -> None:
        row = {
            "agent_fqn": record.agent_fqn,
            "workspace_id": record.workspace_id,
            "assembly_id": record.id,
            "quality_score": float(score.aggregate),
            "quality_subscores": json.dumps(self._subscores(score)),
            "token_count": int(record.token_count_post),
            "ab_test_id": record.ab_test_id,
            "ab_test_group": record.ab_test_group,
            "created_at": record.created_at,
        }
        await self.clickhouse_client.insert(
            self.settings.CONTEXT_ENGINEERING_QUALITY_SCORES_TABLE,
            [row],
            list(row.keys()),
        )

    async def _assert_workspace_access(self, workspace_id: UUID, actor_id: UUID) -> None:
        if self.workspaces_service is None:
            return
        if not hasattr(self.workspaces_service, "get_user_workspace_ids"):
            return
        workspace_ids = await self.workspaces_service.get_user_workspace_ids(actor_id)
        if workspace_id not in workspace_ids:
            raise WorkspaceAuthorizationError(workspace_id)

    async def _commit(self) -> None:
        if hasattr(self.repository.session, "commit"):
            await self.repository.session.commit()

    async def _rollback(self) -> None:
        if hasattr(self.repository.session, "rollback"):
            await self.repository.session.rollback()

    def _profile_response(self, profile: ContextEngineeringProfile) -> ProfileResponse:
        return ProfileResponse(
            id=profile.id,
            name=profile.name,
            description=profile.description,
            is_default=profile.is_default,
            source_config=[SourceConfig.model_validate(item) for item in profile.source_config],
            budget_config=BudgetEnvelope.model_validate(profile.budget_config or {}),
            compaction_strategies=[
                CompactionStrategyType(item) for item in profile.compaction_strategies
            ],
            quality_weights=dict(profile.quality_weights or {}),
            privacy_overrides=dict(profile.privacy_overrides or {}),
            workspace_id=profile.workspace_id,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    def _assignment_response(
        self,
        assignment: ContextProfileAssignment,
    ) -> ProfileAssignmentResponse:
        return ProfileAssignmentResponse(
            id=assignment.id,
            profile_id=assignment.profile_id,
            assignment_level=assignment.assignment_level,
            agent_fqn=assignment.agent_fqn,
            role_type=assignment.role_type,
            workspace_id=assignment.workspace_id,
            created_at=assignment.created_at,
        )

    def _record_response(self, record: Any) -> AssemblyRecordResponse:
        return AssemblyRecordResponse(
            id=record.id,
            execution_id=record.execution_id,
            step_id=record.step_id,
            agent_fqn=record.agent_fqn,
            profile_id=record.profile_id,
            quality_score_pre=record.quality_score_pre,
            quality_score_post=record.quality_score_post,
            token_count_pre=record.token_count_pre,
            token_count_post=record.token_count_post,
            sources_queried=list(record.sources_queried),
            sources_available=list(record.sources_available),
            compaction_applied=record.compaction_applied,
            compaction_actions=list(record.compaction_actions),
            privacy_exclusions=list(record.privacy_exclusions),
            provenance_chain=list(record.provenance_chain),
            bundle_storage_key=record.bundle_storage_key,
            ab_test_id=record.ab_test_id,
            ab_test_group=record.ab_test_group,
            flags=list(record.flags),
            workspace_id=record.workspace_id,
            created_at=record.created_at,
        )

    def _alert_response(self, alert: ContextDriftAlert) -> DriftAlertResponse:
        return DriftAlertResponse(
            id=alert.id,
            agent_fqn=alert.agent_fqn,
            workspace_id=alert.workspace_id,
            historical_mean=alert.historical_mean,
            historical_stddev=alert.historical_stddev,
            recent_mean=alert.recent_mean,
            degradation_delta=alert.degradation_delta,
            analysis_window_days=alert.analysis_window_days,
            suggested_actions=list(alert.suggested_actions),
            resolved_at=alert.resolved_at,
            created_at=alert.created_at,
        )

    def _ab_test_response(self, ab_test: ContextAbTest) -> AbTestResponse:
        return AbTestResponse(
            id=ab_test.id,
            name=ab_test.name,
            status=ab_test.status,
            control_profile_id=ab_test.control_profile_id,
            variant_profile_id=ab_test.variant_profile_id,
            target_agent_fqn=ab_test.target_agent_fqn,
            control_assembly_count=ab_test.control_assembly_count,
            variant_assembly_count=ab_test.variant_assembly_count,
            control_quality_mean=ab_test.control_quality_mean,
            variant_quality_mean=ab_test.variant_quality_mean,
            control_token_mean=ab_test.control_token_mean,
            variant_token_mean=ab_test.variant_token_mean,
            started_at=ab_test.started_at,
            ended_at=ab_test.ended_at,
            workspace_id=ab_test.workspace_id,
            created_at=ab_test.created_at,
            updated_at=ab_test.updated_at,
        )

    def _correlation(
        self,
        correlation_id: UUID | None,
        *,
        workspace_id: UUID,
        execution_id: UUID | None = None,
        goal_id: UUID | None = None,
    ) -> CorrelationContext:
        return CorrelationContext(
            correlation_id=correlation_id or uuid4(),
            workspace_id=workspace_id,
            execution_id=execution_id,
            goal_id=goal_id,
        )

    def _bundle_storage_key(self, workspace_id: UUID, execution_id: UUID, step_id: UUID) -> str:
        return f"{workspace_id}/{execution_id}/{step_id}/bundle.json"

    def _subscores(self, score: ContextQualityScore) -> dict[str, float]:
        return {
            "relevance": score.relevance,
            "freshness": score.freshness,
            "authority": score.authority,
            "contradiction_density": score.contradiction_density,
            "token_efficiency": score.token_efficiency,
            "task_brief_coverage": score.task_brief_coverage,
        }
