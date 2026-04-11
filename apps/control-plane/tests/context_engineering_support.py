from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from platform.context_engineering.models import (
    AbTestStatus,
    ContextAbTest,
    ContextAssemblyRecord,
    ContextDriftAlert,
    ContextEngineeringProfile,
    ContextProfileAssignment,
    ContextSourceType,
    ProfileAssignmentLevel,
)
from platform.context_engineering.schemas import (
    AbTestResponse,
    AssemblyRecordResponse,
    BudgetEnvelope,
    ContextElement,
    ContextProvenanceEntry,
    DriftAlertResponse,
    ProfileAssignmentCreate,
    ProfileAssignmentResponse,
    ProfileCreate,
    ProfileResponse,
    SourceConfig,
)
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from tests.registry_support import SessionStub


def build_profile_create(**overrides: Any) -> ProfileCreate:
    payload: dict[str, Any] = {
        "name": "executor-profile",
        "description": "Default executor profile",
        "source_config": [
            SourceConfig(
                source_type=ContextSourceType.system_instructions,
                priority=100,
                max_elements=1,
            ),
            SourceConfig(
                source_type=ContextSourceType.conversation_history,
                priority=80,
                max_elements=5,
            ),
        ],
        "budget_config": BudgetEnvelope(max_tokens_step=128, max_sources=5),
        "compaction_strategies": ["relevance_truncation", "priority_eviction"],
        "quality_weights": {},
        "privacy_overrides": {},
        "is_default": False,
    }
    payload.update(overrides)
    return ProfileCreate.model_validate(payload)


def build_element(
    *,
    source_type: ContextSourceType = ContextSourceType.conversation_history,
    content: str = "Summarize the latest payment exception",
    token_count: int = 8,
    priority: int = 50,
    origin: str = "conversation:1",
    timestamp: datetime | None = None,
    authority_score: float = 0.8,
    data_classification: str = "public",
    metadata: dict[str, Any] | None = None,
) -> ContextElement:
    return ContextElement(
        source_type=source_type,
        content=content,
        token_count=token_count,
        priority=priority,
        provenance=ContextProvenanceEntry(
            origin=origin,
            timestamp=timestamp or datetime.now(UTC),
            authority_score=authority_score,
            policy_justification="included",
        ),
        data_classification=data_classification,
        metadata=metadata or {},
    )


@dataclass
class EventProducerStub:
    published: list[dict[str, Any]] = field(default_factory=list)

    async def publish(
        self,
        topic: str,
        key: str,
        event_type: str,
        payload: dict[str, Any],
        correlation_ctx: Any,
        source: str,
    ) -> None:
        self.published.append(
            {
                "topic": topic,
                "key": key,
                "event_type": event_type,
                "payload": payload,
                "correlation_ctx": correlation_ctx,
                "source": source,
            }
        )


@dataclass
class PoliciesServiceStub:
    policies: list[Any] = field(default_factory=list)
    calls: list[tuple[UUID, str]] = field(default_factory=list)

    async def get_active_context_policies(self, workspace_id: UUID, agent_fqn: str) -> list[Any]:
        self.calls.append((workspace_id, agent_fqn))
        return list(self.policies)


@dataclass
class RegistryLookupStub:
    agent: Any | None = None

    async def get_by_fqn(self, workspace_id: UUID, fqn: str) -> Any:
        del workspace_id, fqn
        return self.agent


@dataclass
class ExecutionServiceStub:
    workflow_state: Any = field(default_factory=dict)
    tool_outputs: Any = field(default_factory=list)
    reasoning_traces: Any = field(default_factory=list)

    async def get_workflow_state(self, execution_id: UUID, step_id: UUID) -> Any:
        del execution_id, step_id
        return self.workflow_state

    async def get_tool_outputs(self, execution_id: UUID, step_id: UUID) -> Any:
        del execution_id, step_id
        return self.tool_outputs

    async def get_reasoning_traces(self, execution_id: UUID, step_id: UUID) -> Any:
        del execution_id, step_id
        return self.reasoning_traces


@dataclass
class InteractionsServiceStub:
    history: list[Any] = field(default_factory=list)

    async def get_conversation_history(
        self,
        execution_id: UUID,
        step_id: UUID,
        *,
        limit: int,
    ) -> list[Any]:
        del execution_id, step_id
        return list(self.history[:limit])


@dataclass
class MemoryServiceStub:
    items: list[Any] = field(default_factory=list)

    async def search_agent_memory(
        self,
        *,
        workspace_id: UUID,
        agent_fqn: str,
        query: str,
        limit: int,
    ) -> list[Any]:
        del workspace_id, agent_fqn, query
        return list(self.items[:limit])


@dataclass
class ConnectorsServiceStub:
    payloads: list[Any] = field(default_factory=list)

    async def get_connector_payloads(self, execution_id: UUID, step_id: UUID) -> list[Any]:
        del execution_id, step_id
        return list(self.payloads)


@dataclass
class WorkspaceRepoStub:
    workspace: Any | None = None
    goal: Any | None = None

    async def get_workspace_by_id_any(self, workspace_id: UUID) -> Any:
        del workspace_id
        return self.workspace

    async def get_goal_by_gid(self, goal_gid: UUID) -> Any:
        del goal_gid
        return self.goal


@dataclass
class WorkspacesServiceStub:
    workspace_ids: list[UUID] = field(default_factory=list)
    repo: WorkspaceRepoStub = field(default_factory=WorkspaceRepoStub)
    calls: list[UUID] = field(default_factory=list)

    async def get_user_workspace_ids(self, user_id: UUID) -> list[UUID]:
        self.calls.append(user_id)
        return list(self.workspace_ids)


class MemoryContextRepository:
    def __init__(self) -> None:
        self.session = SessionStub()
        self.profiles: dict[UUID, ContextEngineeringProfile] = {}
        self.assignments: dict[UUID, ContextProfileAssignment] = {}
        self.records: dict[UUID, ContextAssemblyRecord] = {}
        self.ab_tests: dict[UUID, ContextAbTest] = {}
        self.alerts: dict[UUID, ContextDriftAlert] = {}

    async def create_profile(self, **fields: Any) -> ContextEngineeringProfile:
        profile = _stamp(ContextEngineeringProfile(**fields))
        self.profiles[profile.id] = profile
        return profile

    async def clear_default_profiles(
        self,
        workspace_id: UUID,
        *,
        exclude_profile_id: UUID | None = None,
    ) -> None:
        for profile in self.profiles.values():
            if profile.workspace_id != workspace_id:
                continue
            if exclude_profile_id is not None and profile.id == exclude_profile_id:
                continue
            profile.is_default = False

    async def get_profile(
        self, workspace_id: UUID, profile_id: UUID
    ) -> ContextEngineeringProfile | None:
        profile = self.profiles.get(profile_id)
        if profile is None or profile.workspace_id != workspace_id:
            return None
        return profile

    async def get_default_profile(self, workspace_id: UUID) -> ContextEngineeringProfile | None:
        for profile in sorted(self.profiles.values(), key=lambda item: (item.created_at, item.id)):
            if profile.workspace_id == workspace_id and profile.is_default:
                return profile
        return None

    async def list_profiles(self, workspace_id: UUID) -> list[ContextEngineeringProfile]:
        return [
            item
            for item in sorted(
                self.profiles.values(), key=lambda profile: (profile.created_at, profile.id)
            )
            if item.workspace_id == workspace_id
        ]

    async def update_profile(
        self,
        profile: ContextEngineeringProfile,
        **fields: Any,
    ) -> ContextEngineeringProfile:
        for key, value in fields.items():
            setattr(profile, key, value)
        profile.updated_at = datetime.now(UTC)
        return profile

    async def delete_profile(self, profile: ContextEngineeringProfile) -> None:
        self.profiles.pop(profile.id, None)

    async def profile_has_assignments(self, profile_id: UUID) -> bool:
        return any(item.profile_id == profile_id for item in self.assignments.values())

    async def profile_has_active_ab_tests(self, profile_id: UUID) -> bool:
        return any(
            item.status == AbTestStatus.active
            and (item.control_profile_id == profile_id or item.variant_profile_id == profile_id)
            for item in self.ab_tests.values()
        )

    async def create_assignment(self, **fields: Any) -> ContextProfileAssignment:
        level = fields["assignment_level"]
        workspace_id = fields["workspace_id"]
        target_agent = fields.get("agent_fqn")
        target_role = fields.get("role_type")
        for assignment in self.assignments.values():
            if assignment.workspace_id != workspace_id:
                continue
            if (
                (
                    level is ProfileAssignmentLevel.agent
                    and assignment.assignment_level is level
                    and assignment.agent_fqn == target_agent
                )
                or (
                    level is ProfileAssignmentLevel.role_type
                    and assignment.assignment_level is level
                    and assignment.role_type == target_role
                )
                or (
                    level is ProfileAssignmentLevel.workspace
                    and assignment.assignment_level is level
                )
            ):
                assignment.profile_id = fields["profile_id"]
                return assignment
        assignment = _stamp(ContextProfileAssignment(**fields))
        self.assignments[assignment.id] = assignment
        return assignment

    async def list_assignments(
        self,
        workspace_id: UUID,
        *,
        profile_id: UUID | None = None,
    ) -> list[ContextProfileAssignment]:
        items = [
            item
            for item in sorted(
                self.assignments.values(),
                key=lambda assignment: (assignment.created_at, assignment.id),
            )
            if item.workspace_id == workspace_id
            and (profile_id is None or item.profile_id == profile_id)
        ]
        return items

    async def get_assignment_by_agent_fqn(
        self,
        workspace_id: UUID,
        agent_fqn: str,
    ) -> ContextProfileAssignment | None:
        return next(
            (
                item
                for item in self.assignments.values()
                if item.workspace_id == workspace_id
                and item.assignment_level is ProfileAssignmentLevel.agent
                and item.agent_fqn == agent_fqn
            ),
            None,
        )

    async def get_assignment_by_role_type(
        self,
        workspace_id: UUID,
        role_type: str,
    ) -> ContextProfileAssignment | None:
        return next(
            (
                item
                for item in self.assignments.values()
                if item.workspace_id == workspace_id
                and item.assignment_level is ProfileAssignmentLevel.role_type
                and item.role_type == role_type
            ),
            None,
        )

    async def get_workspace_default_assignment(
        self,
        workspace_id: UUID,
    ) -> ContextProfileAssignment | None:
        return next(
            (
                item
                for item in self.assignments.values()
                if item.workspace_id == workspace_id
                and item.assignment_level is ProfileAssignmentLevel.workspace
            ),
            None,
        )

    async def find_assembly_record_by_execution_step(
        self,
        workspace_id: UUID,
        execution_id: UUID,
        step_id: UUID,
    ) -> ContextAssemblyRecord | None:
        return next(
            (
                item
                for item in self.records.values()
                if item.workspace_id == workspace_id
                and item.execution_id == execution_id
                and item.step_id == step_id
            ),
            None,
        )

    async def create_assembly_record(self, **fields: Any) -> ContextAssemblyRecord:
        record = _stamp(ContextAssemblyRecord(**fields))
        self.records[record.id] = record
        return record

    async def get_assembly_record(
        self,
        workspace_id: UUID,
        record_id: UUID,
    ) -> ContextAssemblyRecord | None:
        record = self.records.get(record_id)
        if record is None or record.workspace_id != workspace_id:
            return None
        return record

    async def list_assembly_records(
        self,
        workspace_id: UUID,
        *,
        agent_fqn: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ContextAssemblyRecord], int]:
        items = [
            item
            for item in self.records.values()
            if item.workspace_id == workspace_id
            and (agent_fqn is None or item.agent_fqn == agent_fqn)
        ]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return items[offset : offset + limit], len(items)

    async def create_ab_test(self, **fields: Any) -> ContextAbTest:
        test = _stamp(ContextAbTest(**fields))
        self.ab_tests[test.id] = test
        return test

    async def get_ab_test(self, workspace_id: UUID, test_id: UUID) -> ContextAbTest | None:
        test = self.ab_tests.get(test_id)
        if test is None or test.workspace_id != workspace_id:
            return None
        return test

    async def get_active_ab_test(self, workspace_id: UUID, agent_fqn: str) -> ContextAbTest | None:
        candidates = [
            item
            for item in self.ab_tests.values()
            if item.workspace_id == workspace_id
            and item.status is AbTestStatus.active
            and (item.target_agent_fqn is None or item.target_agent_fqn == agent_fqn)
        ]
        candidates.sort(
            key=lambda item: (
                0 if item.target_agent_fqn == agent_fqn else 1,
                item.created_at,
                item.id,
            )
        )
        return candidates[0] if candidates else None

    async def list_ab_tests(
        self,
        workspace_id: UUID,
        *,
        status: AbTestStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ContextAbTest], int]:
        items = [
            item
            for item in self.ab_tests.values()
            if item.workspace_id == workspace_id and (status is None or item.status is status)
        ]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return items[offset : offset + limit], len(items)

    async def update_ab_test_metrics(
        self,
        ab_test: ContextAbTest,
        *,
        group: str,
        quality_score: float,
        token_count: int,
    ) -> ContextAbTest:
        if group == "variant":
            ab_test.variant_quality_mean = _rolling_mean(
                ab_test.variant_quality_mean,
                ab_test.variant_assembly_count,
                quality_score,
            )
            ab_test.variant_token_mean = _rolling_mean(
                ab_test.variant_token_mean,
                ab_test.variant_assembly_count,
                float(token_count),
            )
            ab_test.variant_assembly_count += 1
        else:
            ab_test.control_quality_mean = _rolling_mean(
                ab_test.control_quality_mean,
                ab_test.control_assembly_count,
                quality_score,
            )
            ab_test.control_token_mean = _rolling_mean(
                ab_test.control_token_mean,
                ab_test.control_assembly_count,
                float(token_count),
            )
            ab_test.control_assembly_count += 1
        ab_test.updated_at = datetime.now(UTC)
        return ab_test

    async def complete_ab_test(self, ab_test: ContextAbTest) -> ContextAbTest:
        ab_test.status = AbTestStatus.completed
        ab_test.ended_at = datetime.now(UTC)
        ab_test.updated_at = datetime.now(UTC)
        return ab_test

    async def create_drift_alert(self, **fields: Any) -> ContextDriftAlert:
        alert = _stamp(ContextDriftAlert(**fields))
        self.alerts[alert.id] = alert
        return alert

    async def find_unresolved_drift_alert(
        self,
        workspace_id: UUID,
        agent_fqn: str,
    ) -> ContextDriftAlert | None:
        return next(
            (
                item
                for item in self.alerts.values()
                if item.workspace_id == workspace_id
                and item.agent_fqn == agent_fqn
                and item.resolved_at is None
            ),
            None,
        )

    async def list_drift_alerts(
        self,
        workspace_id: UUID,
        *,
        resolved: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ContextDriftAlert], int]:
        items = [item for item in self.alerts.values() if item.workspace_id == workspace_id]
        if resolved is True:
            items = [item for item in items if item.resolved_at is not None]
        elif resolved is False:
            items = [item for item in items if item.resolved_at is None]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return items[offset : offset + limit], len(items)

    async def resolve_drift_alert(self, alert: ContextDriftAlert) -> ContextDriftAlert:
        alert.resolved_at = datetime.now(UTC)
        alert.updated_at = datetime.now(UTC)
        return alert


def profile_response(profile: ContextEngineeringProfile) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        is_default=profile.is_default,
        source_config=[SourceConfig.model_validate(item) for item in profile.source_config],
        budget_config=BudgetEnvelope.model_validate(profile.budget_config),
        compaction_strategies=list(profile.compaction_strategies),
        quality_weights=dict(profile.quality_weights),
        privacy_overrides=dict(profile.privacy_overrides),
        workspace_id=profile.workspace_id,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def assignment_response(assignment: ContextProfileAssignment) -> ProfileAssignmentResponse:
    return ProfileAssignmentResponse(
        id=assignment.id,
        profile_id=assignment.profile_id,
        assignment_level=assignment.assignment_level,
        agent_fqn=assignment.agent_fqn,
        role_type=assignment.role_type,
        workspace_id=assignment.workspace_id,
        created_at=assignment.created_at,
    )


def ab_test_response(test: ContextAbTest) -> AbTestResponse:
    return AbTestResponse(
        id=test.id,
        name=test.name,
        status=test.status,
        control_profile_id=test.control_profile_id,
        variant_profile_id=test.variant_profile_id,
        target_agent_fqn=test.target_agent_fqn,
        control_assembly_count=test.control_assembly_count,
        variant_assembly_count=test.variant_assembly_count,
        control_quality_mean=test.control_quality_mean,
        variant_quality_mean=test.variant_quality_mean,
        control_token_mean=test.control_token_mean,
        variant_token_mean=test.variant_token_mean,
        started_at=test.started_at,
        ended_at=test.ended_at,
        workspace_id=test.workspace_id,
        created_at=test.created_at,
        updated_at=test.updated_at,
    )


def record_response(record: ContextAssemblyRecord) -> AssemblyRecordResponse:
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


def drift_alert_response(alert: ContextDriftAlert) -> DriftAlertResponse:
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


@dataclass
class RouterContextEngineeringServiceStub:
    workspace_id: UUID
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)

    async def create_profile(
        self, workspace_id: UUID, payload: ProfileCreate, actor_id: UUID
    ) -> ProfileResponse:
        self.calls.append(("create_profile", (workspace_id, payload, actor_id), {}))
        profile = _stamp(
            ContextEngineeringProfile(
                workspace_id=workspace_id,
                name=payload.name,
                description=payload.description,
                is_default=payload.is_default,
                source_config=[item.model_dump(mode="json") for item in payload.source_config],
                budget_config=payload.budget_config.model_dump(mode="json"),
                compaction_strategies=[item.value for item in payload.compaction_strategies],
                quality_weights=dict(payload.quality_weights),
                privacy_overrides=dict(payload.privacy_overrides),
            )
        )
        return profile_response(profile)

    async def list_profiles(self, workspace_id: UUID, actor_id: UUID) -> Any:
        self.calls.append(("list_profiles", (workspace_id, actor_id), {}))
        profile = await self.create_profile(workspace_id, build_profile_create(), actor_id)
        return SimpleNamespace(items=[profile], total=1)

    async def get_profile(
        self, workspace_id: UUID, profile_id: UUID, actor_id: UUID
    ) -> ProfileResponse:
        self.calls.append(("get_profile", (workspace_id, profile_id, actor_id), {}))
        profile = await self.create_profile(
            workspace_id, build_profile_create(name="resolved"), actor_id
        )
        return profile

    async def update_profile(
        self,
        workspace_id: UUID,
        profile_id: UUID,
        payload: ProfileCreate,
        actor_id: UUID,
    ) -> ProfileResponse:
        self.calls.append(("update_profile", (workspace_id, profile_id, payload, actor_id), {}))
        return await self.create_profile(workspace_id, payload, actor_id)

    async def delete_profile(self, workspace_id: UUID, profile_id: UUID, actor_id: UUID) -> None:
        self.calls.append(("delete_profile", (workspace_id, profile_id, actor_id), {}))

    async def assign_profile(
        self,
        workspace_id: UUID,
        profile_id: UUID,
        payload: ProfileAssignmentCreate,
        actor_id: UUID,
    ) -> ProfileAssignmentResponse:
        self.calls.append(("assign_profile", (workspace_id, profile_id, payload, actor_id), {}))
        assignment = _stamp(
            ContextProfileAssignment(
                workspace_id=workspace_id,
                profile_id=profile_id,
                assignment_level=payload.assignment_level,
                agent_fqn=payload.agent_fqn,
                role_type=payload.role_type,
            )
        )
        return assignment_response(assignment)

    async def list_assembly_records(self, workspace_id: UUID, actor_id: UUID, **kwargs: Any) -> Any:
        self.calls.append(("list_assembly_records", (workspace_id, actor_id), kwargs))
        record = _stamp(
            ContextAssemblyRecord(
                workspace_id=workspace_id,
                execution_id=uuid4(),
                step_id=uuid4(),
                agent_fqn="finance:agent",
                profile_id=None,
                quality_score_pre=0.8,
                quality_score_post=0.7,
                token_count_pre=120,
                token_count_post=90,
                sources_queried=["system_instructions"],
                sources_available=["system_instructions"],
                compaction_applied=True,
                compaction_actions=[],
                privacy_exclusions=[],
                provenance_chain=[],
                bundle_storage_key="bundle.json",
                ab_test_id=None,
                ab_test_group=None,
                flags=[],
            )
        )
        return SimpleNamespace(items=[record_response(record)], total=1, limit=20, offset=0)

    async def get_assembly_record(
        self,
        workspace_id: UUID,
        record_id: UUID,
        actor_id: UUID,
    ) -> AssemblyRecordResponse:
        self.calls.append(("get_assembly_record", (workspace_id, record_id, actor_id), {}))
        response = await self.list_assembly_records(workspace_id, actor_id)
        return response.items[0]

    async def list_drift_alerts(self, workspace_id: UUID, actor_id: UUID, **kwargs: Any) -> Any:
        self.calls.append(("list_drift_alerts", (workspace_id, actor_id), kwargs))
        alert = _stamp(
            ContextDriftAlert(
                workspace_id=workspace_id,
                agent_fqn="finance:agent",
                historical_mean=0.8,
                historical_stddev=0.05,
                recent_mean=0.5,
                degradation_delta=0.3,
                analysis_window_days=7,
                suggested_actions=["Review compaction"],
            )
        )
        return SimpleNamespace(items=[drift_alert_response(alert)], total=1, limit=20, offset=0)

    async def create_ab_test(
        self, workspace_id: UUID, payload: Any, actor_id: UUID
    ) -> AbTestResponse:
        self.calls.append(("create_ab_test", (workspace_id, payload, actor_id), {}))
        test = _stamp(
            ContextAbTest(
                workspace_id=workspace_id,
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
        )
        return ab_test_response(test)

    async def list_ab_tests(self, workspace_id: UUID, actor_id: UUID, **kwargs: Any) -> Any:
        self.calls.append(("list_ab_tests", (workspace_id, actor_id), kwargs))
        test = await self.create_ab_test(
            workspace_id,
            SimpleNamespace(
                name="experiment",
                control_profile_id=uuid4(),
                variant_profile_id=uuid4(),
                target_agent_fqn=None,
            ),
            actor_id,
        )
        return SimpleNamespace(items=[test], total=1, limit=20, offset=0)

    async def get_ab_test(
        self, workspace_id: UUID, test_id: UUID, actor_id: UUID
    ) -> AbTestResponse:
        self.calls.append(("get_ab_test", (workspace_id, test_id, actor_id), {}))
        return (await self.list_ab_tests(workspace_id, actor_id)).items[0]

    async def end_ab_test(
        self, workspace_id: UUID, test_id: UUID, actor_id: UUID
    ) -> AbTestResponse:
        self.calls.append(("end_ab_test", (workspace_id, test_id, actor_id), {}))
        response = await self.get_ab_test(workspace_id, test_id, actor_id)
        return response.model_copy(
            update={"status": AbTestStatus.completed, "ended_at": datetime.now(UTC)}
        )


def _stamp(model: Any) -> Any:
    now = datetime.now(UTC)
    if getattr(model, "id", None) is None:
        model.id = uuid4()
    if hasattr(model, "created_at") and getattr(model, "created_at", None) is None:
        model.created_at = now
    if hasattr(model, "updated_at") and getattr(model, "updated_at", None) is None:
        model.updated_at = now
    return model


def _rolling_mean(current_mean: float | None, current_count: int, value: float) -> float:
    if current_mean is None or current_count <= 0:
        return value
    return ((current_mean * current_count) + value) / (current_count + 1)
