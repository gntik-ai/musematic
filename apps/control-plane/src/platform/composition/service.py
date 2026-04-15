from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from platform.common.config import PlatformSettings
from platform.composition.events import AUDIT_TO_EVENT, CompositionEventPublisher
from platform.composition.exceptions import (
    BlueprintNotFoundError,
    CompositionRequestNotFoundError,
    DescriptionTooLongError,
    InvalidOverridePathError,
    LLMServiceUnavailableError,
)
from platform.composition.generators.agent import AgentBlueprintGenerator
from platform.composition.generators.fleet import FleetBlueprintGenerator
from platform.composition.llm.client import LLMCompositionClient
from platform.composition.models import (
    AgentBlueprint,
    CompositionAuditEntry,
    CompositionAuditEventType,
    CompositionRequest,
    CompositionRequestStatus,
    CompositionRequestType,
    CompositionValidation,
    FleetBlueprint,
)
from platform.composition.repository import CompositionRepository
from platform.composition.schemas import (
    AgentBlueprintGenerateRequest,
    AgentBlueprintOverrideRequest,
    AgentBlueprintRaw,
    AgentBlueprintResponse,
    BlueprintOverrideItem,
    CheckResult,
    CompositionAuditEntryResponse,
    CompositionAuditListResponse,
    CompositionRequestListResponse,
    CompositionRequestResponse,
    CompositionValidationResponse,
    FleetBlueprintGenerateRequest,
    FleetBlueprintOverrideRequest,
    FleetBlueprintRaw,
    FleetBlueprintResponse,
    WorkspaceCompositionContext,
)
from platform.composition.validation.validator import BlueprintValidator
from typing import Any, Protocol
from uuid import UUID


class CompositionServiceInterface(Protocol):
    """Interface exposed to contexts that consume generated blueprints."""

    async def get_latest_agent_blueprint(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> AgentBlueprintResponse | None: ...

    async def get_latest_fleet_blueprint(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> FleetBlueprintResponse | None: ...


@dataclass(frozen=True)
class WorkspaceServices:
    """Service interfaces used by composition."""

    registry: Any
    policy: Any
    connector: Any


class CompositionService:
    """Orchestrate AI-assisted blueprint composition workflows."""

    def __init__(
        self,
        *,
        repository: CompositionRepository,
        publisher: CompositionEventPublisher,
        llm_client: LLMCompositionClient,
        settings: PlatformSettings,
        services: WorkspaceServices,
        agent_generator: AgentBlueprintGenerator | None = None,
        fleet_generator: FleetBlueprintGenerator | None = None,
        validator: BlueprintValidator | None = None,
    ) -> None:
        self.repository = repository
        self.publisher = publisher
        self.llm_client = llm_client
        self.settings = settings
        self.services = services
        self.agent_generator = agent_generator or AgentBlueprintGenerator(llm_client, settings)
        self.fleet_generator = fleet_generator or FleetBlueprintGenerator(llm_client, settings)
        self.validator = validator or BlueprintValidator(
            registry_service=services.registry,
            policy_service=services.policy,
            connector_service=services.connector,
        )

    async def generate_agent_blueprint(
        self,
        payload: AgentBlueprintGenerateRequest,
        actor_id: UUID,
    ) -> AgentBlueprintResponse:
        """Generate and persist an agent blueprint."""
        self._validate_description(payload.description)
        request = await self.repository.create_request(
            CompositionRequest(
                workspace_id=payload.workspace_id,
                request_type=CompositionRequestType.agent.value,
                description=payload.description,
                requested_by=actor_id,
                status=CompositionRequestStatus.pending.value,
            )
        )
        start = time.perf_counter()
        try:
            raw = await self.agent_generator.generate(
                payload.description,
                payload.workspace_id,
                await self._workspace_context(payload.workspace_id),
            )
            generation_time_ms = int((time.perf_counter() - start) * 1000)
            blueprint = await self.repository.create_agent_blueprint(
                self._agent_model(request, raw, generation_time_ms)
            )
            request.status = CompositionRequestStatus.completed.value
            request.llm_model_used = self.settings.composition.llm_model
            request.generation_time_ms = generation_time_ms
            await self.repository.session.flush()
            await self._record_audit(
                request.id,
                payload.workspace_id,
                CompositionAuditEventType.blueprint_generated.value,
                actor_id,
                {
                    "request_type": "agent",
                    "blueprint_id": str(blueprint.id),
                    "version": blueprint.version,
                },
            )
            return self._agent_response(blueprint)
        except LLMServiceUnavailableError:
            request.status = CompositionRequestStatus.failed.value
            await self.repository.session.flush()
            await self._record_audit(
                request.id,
                payload.workspace_id,
                CompositionAuditEventType.generation_failed.value,
                actor_id,
                {"request_type": "agent"},
            )
            raise

    async def generate_fleet_blueprint(
        self,
        payload: FleetBlueprintGenerateRequest,
        actor_id: UUID,
    ) -> FleetBlueprintResponse:
        """Generate and persist a fleet blueprint."""
        self._validate_description(payload.description)
        request = await self.repository.create_request(
            CompositionRequest(
                workspace_id=payload.workspace_id,
                request_type=CompositionRequestType.fleet.value,
                description=payload.description,
                requested_by=actor_id,
                status=CompositionRequestStatus.pending.value,
            )
        )
        start = time.perf_counter()
        try:
            raw = await self.fleet_generator.generate(
                payload.description,
                payload.workspace_id,
                await self._workspace_context(payload.workspace_id),
            )
            generation_time_ms = int((time.perf_counter() - start) * 1000)
            blueprint = await self.repository.create_fleet_blueprint(
                self._fleet_model(request, raw, generation_time_ms)
            )
            request.status = CompositionRequestStatus.completed.value
            request.llm_model_used = self.settings.composition.llm_model
            request.generation_time_ms = generation_time_ms
            await self.repository.session.flush()
            await self._record_audit(
                request.id,
                payload.workspace_id,
                CompositionAuditEventType.blueprint_generated.value,
                actor_id,
                {
                    "request_type": "fleet",
                    "blueprint_id": str(blueprint.id),
                    "version": blueprint.version,
                },
            )
            return self._fleet_response(blueprint)
        except LLMServiceUnavailableError:
            request.status = CompositionRequestStatus.failed.value
            await self.repository.session.flush()
            await self._record_audit(
                request.id,
                payload.workspace_id,
                CompositionAuditEventType.generation_failed.value,
                actor_id,
                {"request_type": "fleet"},
            )
            raise

    async def get_agent_blueprint(
        self,
        blueprint_id: UUID,
        workspace_id: UUID,
    ) -> AgentBlueprintResponse:
        """Return an agent blueprint."""
        blueprint = await self.repository.get_agent_blueprint(blueprint_id, workspace_id)
        if blueprint is None:
            raise BlueprintNotFoundError(blueprint_id)
        return self._agent_response(blueprint)

    async def get_fleet_blueprint(
        self,
        blueprint_id: UUID,
        workspace_id: UUID,
    ) -> FleetBlueprintResponse:
        """Return a fleet blueprint."""
        blueprint = await self.repository.get_fleet_blueprint(blueprint_id, workspace_id)
        if blueprint is None:
            raise BlueprintNotFoundError(blueprint_id)
        return self._fleet_response(blueprint)

    async def get_latest_agent_blueprint(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> AgentBlueprintResponse | None:
        """Return latest agent blueprint for a request."""
        blueprint = await self.repository.get_latest_agent_blueprint(request_id, workspace_id)
        return self._agent_response(blueprint) if blueprint is not None else None

    async def get_latest_fleet_blueprint(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> FleetBlueprintResponse | None:
        """Return latest fleet blueprint for a request."""
        blueprint = await self.repository.get_latest_fleet_blueprint(request_id, workspace_id)
        return self._fleet_response(blueprint) if blueprint is not None else None

    async def validate_agent_blueprint(
        self,
        blueprint_id: UUID,
        workspace_id: UUID,
        actor_id: UUID | None = None,
    ) -> CompositionValidationResponse:
        """Validate an agent blueprint and persist validation results."""
        blueprint = await self.repository.get_agent_blueprint(blueprint_id, workspace_id)
        if blueprint is None:
            raise BlueprintNotFoundError(blueprint_id)
        result = await self.validator.validate_agent(blueprint, workspace_id)
        validation = await self._persist_validation(blueprint, None, workspace_id, result)
        await self._record_audit(
            blueprint.request_id,
            workspace_id,
            CompositionAuditEventType.blueprint_validated.value,
            actor_id,
            {
                "request_type": "agent",
                "blueprint_id": str(blueprint.id),
                "overall_valid": validation.overall_valid,
            },
        )
        return self._validation_response(validation, blueprint.id)

    async def validate_fleet_blueprint(
        self,
        blueprint_id: UUID,
        workspace_id: UUID,
        actor_id: UUID | None = None,
    ) -> CompositionValidationResponse:
        """Validate a fleet blueprint and persist validation results."""
        blueprint = await self.repository.get_fleet_blueprint(blueprint_id, workspace_id)
        if blueprint is None:
            raise BlueprintNotFoundError(blueprint_id)
        result = await self.validator.validate_fleet(blueprint, workspace_id)
        validation = await self._persist_validation(None, blueprint, workspace_id, result)
        await self._record_audit(
            blueprint.request_id,
            workspace_id,
            CompositionAuditEventType.blueprint_validated.value,
            actor_id,
            {
                "request_type": "fleet",
                "blueprint_id": str(blueprint.id),
                "overall_valid": validation.overall_valid,
            },
        )
        return self._validation_response(validation, blueprint.id)

    async def override_agent_blueprint(
        self,
        blueprint_id: UUID,
        payload: AgentBlueprintOverrideRequest,
        actor_id: UUID,
        workspace_id: UUID,
    ) -> AgentBlueprintResponse:
        """Create a new agent blueprint version with human overrides applied."""
        current = await self.repository.get_agent_blueprint(blueprint_id, workspace_id)
        if current is None:
            raise BlueprintNotFoundError(blueprint_id)
        data = self._agent_payload(current)
        applied = _apply_overrides(data, payload.overrides)
        blueprint = await self.repository.create_agent_blueprint(
            AgentBlueprint(
                request_id=current.request_id,
                version=current.version + 1,
                workspace_id=workspace_id,
                model_config=data["model_config"],
                tool_selections=data["tool_selections"],
                connector_suggestions=data["connector_suggestions"],
                policy_recommendations=data["policy_recommendations"],
                context_profile=data["context_profile"],
                maturity_estimate=data["maturity_estimate"],
                maturity_reasoning=data["maturity_reasoning"],
                confidence_score=data["confidence_score"],
                low_confidence=data["low_confidence"],
                follow_up_questions=data["follow_up_questions"],
                llm_reasoning_summary=data["llm_reasoning_summary"],
                alternatives_considered=data["alternatives_considered"],
            )
        )
        await self._record_audit(
            current.request_id,
            workspace_id,
            CompositionAuditEventType.blueprint_overridden.value,
            actor_id,
            {"request_type": "agent", "blueprint_id": str(blueprint.id), "overrides": applied},
        )
        return self._agent_response(blueprint)

    async def override_fleet_blueprint(
        self,
        blueprint_id: UUID,
        payload: FleetBlueprintOverrideRequest,
        actor_id: UUID,
        workspace_id: UUID,
    ) -> FleetBlueprintResponse:
        """Create a new fleet blueprint version with human overrides applied."""
        current = await self.repository.get_fleet_blueprint(blueprint_id, workspace_id)
        if current is None:
            raise BlueprintNotFoundError(blueprint_id)
        data = self._fleet_payload(current)
        applied = _apply_overrides(data, payload.overrides)
        blueprint = await self.repository.create_fleet_blueprint(
            FleetBlueprint(
                request_id=current.request_id,
                version=current.version + 1,
                workspace_id=workspace_id,
                topology_type=data["topology_type"],
                member_count=len(data["member_roles"]),
                member_roles=data["member_roles"],
                orchestration_rules=data["orchestration_rules"],
                delegation_rules=data["delegation_rules"],
                escalation_rules=data["escalation_rules"],
                confidence_score=data["confidence_score"],
                low_confidence=data["low_confidence"],
                follow_up_questions=data["follow_up_questions"],
                llm_reasoning_summary=data["llm_reasoning_summary"],
                alternatives_considered=data["alternatives_considered"],
                single_agent_suggestion=data["single_agent_suggestion"],
            )
        )
        await self._record_audit(
            current.request_id,
            workspace_id,
            CompositionAuditEventType.blueprint_overridden.value,
            actor_id,
            {"request_type": "fleet", "blueprint_id": str(blueprint.id), "overrides": applied},
        )
        return self._fleet_response(blueprint)

    async def list_audit_entries(
        self,
        request_id: UUID,
        workspace_id: UUID,
        *,
        event_type: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> CompositionAuditListResponse:
        """Return audit entries for a request."""
        if not await self.repository.request_exists(request_id, workspace_id):
            raise CompositionRequestNotFoundError(request_id)
        items, next_cursor = await self.repository.get_audit_entries(
            request_id,
            workspace_id,
            event_type_filter=event_type,
            cursor=cursor,
            limit=limit,
        )
        return CompositionAuditListResponse(
            items=[self._audit_response(item) for item in items],
            next_cursor=next_cursor,
        )

    async def get_request(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> CompositionRequestResponse:
        """Return a composition request."""
        request = await self.repository.get_request(request_id, workspace_id)
        if request is None:
            raise CompositionRequestNotFoundError(request_id)
        return self._request_response(request)

    async def list_requests(
        self,
        workspace_id: UUID,
        *,
        request_type: str | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> CompositionRequestListResponse:
        """Return composition requests for a workspace."""
        items, next_cursor = await self.repository.list_requests(
            workspace_id,
            request_type=request_type,
            status=status,
            cursor=cursor,
            limit=limit,
        )
        return CompositionRequestListResponse(
            items=[self._request_response(item) for item in items],
            next_cursor=next_cursor,
        )

    def _validate_description(self, description: str) -> None:
        if len(description) > self.settings.composition.description_max_chars:
            raise DescriptionTooLongError(self.settings.composition.description_max_chars)

    async def _workspace_context(self, workspace_id: UUID) -> WorkspaceCompositionContext:
        tools = await _optional_call(self.services.registry, "get_available_tools", workspace_id)
        models = await _optional_call(self.services.registry, "get_available_models", workspace_id)
        connectors = await _optional_call(
            self.services.connector,
            "list_workspace_connectors",
            workspace_id,
        )
        policies = await _optional_call(self.services.policy, "list_active_policies", workspace_id)
        return WorkspaceCompositionContext(
            available_tools=[
                _safe_mapping(item, ("name", "capability_description", "tool_type"))
                for item in tools
            ],
            available_models=[
                _safe_mapping(item, ("identifier", "provider", "tier")) for item in models
            ],
            available_connectors=[
                _safe_mapping(item, ("connector_name", "connector_type", "status"))
                for item in connectors
            ],
            active_policies=[
                _safe_mapping(item, ("name", "description", "scope")) for item in policies
            ],
        )

    def _agent_model(
        self,
        request: CompositionRequest,
        raw: AgentBlueprintRaw,
        generation_time_ms: int,
    ) -> AgentBlueprint:
        del generation_time_ms
        confidence = raw.confidence_score
        return AgentBlueprint(
            request_id=request.id,
            version=1,
            workspace_id=request.workspace_id,
            model_config=raw.model_payload,
            tool_selections=[item.model_dump(mode="json") for item in raw.tool_selections],
            connector_suggestions=[
                item.model_dump(mode="json") for item in raw.connector_suggestions
            ],
            policy_recommendations=[
                item.model_dump(mode="json") for item in raw.policy_recommendations
            ],
            context_profile=raw.context_profile.model_dump(mode="json"),
            maturity_estimate=raw.maturity_estimate,
            maturity_reasoning=raw.maturity_reasoning,
            confidence_score=confidence,
            low_confidence=confidence < self.settings.composition.low_confidence_threshold,
            follow_up_questions=[item.model_dump(mode="json") for item in raw.follow_up_questions],
            llm_reasoning_summary=raw.llm_reasoning_summary,
            alternatives_considered=[
                item.model_dump(mode="json") for item in raw.alternatives_considered
            ],
        )

    def _fleet_model(
        self,
        request: CompositionRequest,
        raw: FleetBlueprintRaw,
        generation_time_ms: int,
    ) -> FleetBlueprint:
        del generation_time_ms
        confidence = raw.confidence_score
        member_roles = [item.model_dump(mode="json") for item in raw.member_roles]
        return FleetBlueprint(
            request_id=request.id,
            version=1,
            workspace_id=request.workspace_id,
            topology_type=raw.topology_type,
            member_count=len(member_roles),
            member_roles=member_roles,
            orchestration_rules=[item.model_dump(mode="json") for item in raw.orchestration_rules],
            delegation_rules=[item.model_dump(mode="json") for item in raw.delegation_rules],
            escalation_rules=[item.model_dump(mode="json") for item in raw.escalation_rules],
            confidence_score=confidence,
            low_confidence=confidence < self.settings.composition.low_confidence_threshold,
            follow_up_questions=[item.model_dump(mode="json") for item in raw.follow_up_questions],
            llm_reasoning_summary=raw.llm_reasoning_summary,
            alternatives_considered=[
                item.model_dump(mode="json") for item in raw.alternatives_considered
            ],
            single_agent_suggestion=raw.single_agent_suggestion,
        )

    async def _persist_validation(
        self,
        agent_blueprint: AgentBlueprint | None,
        fleet_blueprint: FleetBlueprint | None,
        workspace_id: UUID,
        result: dict[str, CheckResult | None | bool],
    ) -> CompositionValidation:
        tools = _check_result(result["tools_check"])
        model = _check_result(result["model_check"])
        connectors = _check_result(result["connectors_check"])
        policy = _check_result(result["policy_check"])
        cycle = _nullable_check_result(result["cycle_check"])
        return await self.repository.insert_validation(
            CompositionValidation(
                workspace_id=workspace_id,
                agent_blueprint_id=agent_blueprint.id if agent_blueprint is not None else None,
                fleet_blueprint_id=fleet_blueprint.id if fleet_blueprint is not None else None,
                overall_valid=bool(result["overall_valid"]),
                tools_check_passed=tools.passed,
                tools_check_details=_details_payload(tools),
                model_check_passed=model.passed,
                model_check_details=_details_payload(model),
                connectors_check_passed=connectors.passed,
                connectors_check_details=_details_payload(connectors),
                policy_check_passed=policy.passed,
                policy_check_details=_details_payload(policy),
                cycle_check_passed=cycle.passed if cycle is not None else None,
                cycle_check_details=_details_payload(cycle) if cycle is not None else None,
            )
        )

    async def _record_audit(
        self,
        request_id: UUID,
        workspace_id: UUID,
        event_type: str,
        actor_id: UUID | None,
        payload: dict[str, Any],
    ) -> None:
        await self.repository.insert_audit_entry(
            CompositionAuditEntry(
                request_id=request_id,
                workspace_id=workspace_id,
                event_type=event_type,
                actor_id=actor_id,
                payload=payload,
            )
        )
        await self.publisher.publish(
            AUDIT_TO_EVENT[event_type],
            request_id,
            workspace_id,
            payload,
            actor_id=actor_id,
        )

    def _agent_response(self, blueprint: AgentBlueprint) -> AgentBlueprintResponse:
        request = blueprint.request
        return AgentBlueprintResponse(
            request_id=blueprint.request_id,
            blueprint_id=blueprint.id,
            version=blueprint.version,
            workspace_id=blueprint.workspace_id,
            description=request.description,
            model_config_data=blueprint.model_config,
            tool_selections=blueprint.tool_selections,
            connector_suggestions=blueprint.connector_suggestions,
            policy_recommendations=blueprint.policy_recommendations,
            context_profile=blueprint.context_profile,
            maturity_estimate=blueprint.maturity_estimate,
            maturity_reasoning=blueprint.maturity_reasoning,
            confidence_score=blueprint.confidence_score,
            low_confidence=blueprint.low_confidence,
            follow_up_questions=blueprint.follow_up_questions,
            llm_reasoning_summary=blueprint.llm_reasoning_summary,
            alternatives_considered=blueprint.alternatives_considered,
            generation_time_ms=request.generation_time_ms,
            created_at=blueprint.created_at,
        )

    def _fleet_response(self, blueprint: FleetBlueprint) -> FleetBlueprintResponse:
        request = blueprint.request
        return FleetBlueprintResponse(
            request_id=blueprint.request_id,
            blueprint_id=blueprint.id,
            version=blueprint.version,
            workspace_id=blueprint.workspace_id,
            description=request.description,
            topology_type=blueprint.topology_type,
            member_count=blueprint.member_count,
            member_roles=blueprint.member_roles,
            orchestration_rules=blueprint.orchestration_rules,
            delegation_rules=blueprint.delegation_rules,
            escalation_rules=blueprint.escalation_rules,
            single_agent_suggestion=blueprint.single_agent_suggestion,
            confidence_score=blueprint.confidence_score,
            low_confidence=blueprint.low_confidence,
            follow_up_questions=blueprint.follow_up_questions,
            llm_reasoning_summary=blueprint.llm_reasoning_summary,
            alternatives_considered=blueprint.alternatives_considered,
            generation_time_ms=request.generation_time_ms,
            created_at=blueprint.created_at,
        )

    def _validation_response(
        self,
        validation: CompositionValidation,
        blueprint_id: UUID,
    ) -> CompositionValidationResponse:
        cycle = (
            CheckResult(
                passed=validation.cycle_check_passed,
                details=validation.cycle_check_details or {},
                status=_status(validation.cycle_check_passed),
            )
            if validation.cycle_check_details is not None
            else None
        )
        return CompositionValidationResponse(
            validation_id=validation.id,
            blueprint_id=blueprint_id,
            overall_valid=validation.overall_valid,
            tools_check=CheckResult(
                passed=validation.tools_check_passed,
                details=validation.tools_check_details,
                status=_status(validation.tools_check_passed),
            ),
            model_check=CheckResult(
                passed=validation.model_check_passed,
                details=validation.model_check_details,
                status=_status(validation.model_check_passed),
            ),
            connectors_check=CheckResult(
                passed=validation.connectors_check_passed,
                details=validation.connectors_check_details,
                status=_status(validation.connectors_check_passed),
            ),
            policy_check=CheckResult(
                passed=validation.policy_check_passed,
                details=validation.policy_check_details,
                status=_status(validation.policy_check_passed),
            ),
            cycle_check=cycle,
            validated_at=validation.created_at,
        )

    def _audit_response(self, entry: CompositionAuditEntry) -> CompositionAuditEntryResponse:
        return CompositionAuditEntryResponse(
            entry_id=entry.id,
            request_id=entry.request_id,
            event_type=entry.event_type,
            actor_id=entry.actor_id,
            payload=entry.payload,
            created_at=entry.created_at,
        )

    def _request_response(self, request: CompositionRequest) -> CompositionRequestResponse:
        return CompositionRequestResponse(
            request_id=request.id,
            workspace_id=request.workspace_id,
            request_type=request.request_type,
            description=request.description,
            requested_by=request.requested_by,
            status=request.status,
            llm_model_used=request.llm_model_used,
            generation_time_ms=request.generation_time_ms,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )

    def _agent_payload(self, blueprint: AgentBlueprint) -> dict[str, Any]:
        return {
            "model_config": copy.deepcopy(blueprint.model_config),
            "tool_selections": copy.deepcopy(blueprint.tool_selections),
            "connector_suggestions": copy.deepcopy(blueprint.connector_suggestions),
            "policy_recommendations": copy.deepcopy(blueprint.policy_recommendations),
            "context_profile": copy.deepcopy(blueprint.context_profile),
            "maturity_estimate": blueprint.maturity_estimate,
            "maturity_reasoning": blueprint.maturity_reasoning,
            "confidence_score": blueprint.confidence_score,
            "low_confidence": blueprint.low_confidence,
            "follow_up_questions": copy.deepcopy(blueprint.follow_up_questions),
            "llm_reasoning_summary": blueprint.llm_reasoning_summary,
            "alternatives_considered": copy.deepcopy(blueprint.alternatives_considered),
        }

    def _fleet_payload(self, blueprint: FleetBlueprint) -> dict[str, Any]:
        return {
            "topology_type": blueprint.topology_type,
            "member_roles": copy.deepcopy(blueprint.member_roles),
            "orchestration_rules": copy.deepcopy(blueprint.orchestration_rules),
            "delegation_rules": copy.deepcopy(blueprint.delegation_rules),
            "escalation_rules": copy.deepcopy(blueprint.escalation_rules),
            "confidence_score": blueprint.confidence_score,
            "low_confidence": blueprint.low_confidence,
            "follow_up_questions": copy.deepcopy(blueprint.follow_up_questions),
            "llm_reasoning_summary": blueprint.llm_reasoning_summary,
            "alternatives_considered": copy.deepcopy(blueprint.alternatives_considered),
            "single_agent_suggestion": blueprint.single_agent_suggestion,
        }


async def _optional_call(service: Any, method_name: str, *args: object) -> list[Any]:
    method = getattr(service, method_name, None)
    if not callable(method):
        return []
    try:
        result = await method(*args)
    except Exception:
        return []
    return list(result or [])


def _safe_mapping(item: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in fields:
        if isinstance(item, dict):
            value = item.get(field)
        else:
            value = getattr(item, field, None)
        if value is not None:
            output[field] = str(value)
    return output


def _apply_overrides(
    data: dict[str, Any],
    overrides: list[BlueprintOverrideItem],
) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    for item in overrides:
        old_value = _set_path(data, item.field_path, item.new_value)
        applied.append(
            {
                "field_path": item.field_path,
                "old_value": old_value,
                "new_value": item.new_value,
                "reason": item.reason,
            }
        )
    return applied


def _set_path(data: dict[str, Any], field_path: str, value: Any) -> Any:
    parts = field_path.split(".")
    cursor: Any = data
    for part in parts[:-1]:
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
            continue
        raise InvalidOverridePathError(field_path)
    leaf = parts[-1]
    if not isinstance(cursor, dict) or leaf not in cursor:
        raise InvalidOverridePathError(field_path)
    old_value = cursor[leaf]
    cursor[leaf] = value
    return old_value


def _check_result(value: CheckResult | None | bool) -> CheckResult:
    if not isinstance(value, CheckResult):
        raise TypeError("Expected CheckResult")
    return value


def _nullable_check_result(value: CheckResult | None | bool) -> CheckResult | None:
    if value is None:
        return None
    return _check_result(value)


def _details_payload(result: CheckResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "details": result.details,
        "remediation": result.remediation,
    }


def _status(passed: bool | None) -> str:
    return "validation_unavailable" if passed is None else "ok"
