from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import ValidationError
from platform.workflows.compiler import WorkflowCompiler
from platform.workflows.events import (
    TriggerFiredEvent,
    WorkflowPublishedEvent,
    publish_trigger_fired,
    publish_workflow_published,
)
from platform.workflows.exceptions import TriggerNotFoundError, WorkflowNotFoundError
from platform.workflows.ir import WorkflowIR
from platform.workflows.models import (
    TriggerType,
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowTriggerDefinition,
    WorkflowVersion,
)
from platform.workflows.repository import WorkflowRepository
from platform.workflows.schemas import (
    TriggerCreate,
    TriggerListResponse,
    TriggerResponse,
    WorkflowCreate,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowUpdate,
    WorkflowVersionResponse,
)
from typing import Any
from uuid import UUID, uuid4


class WorkflowService:
    """Provide workflow operations."""
    def __init__(
        self,
        *,
        repository: WorkflowRepository,
        settings: PlatformSettings,
        producer: EventProducer | None,
        scheduler: Any | None = None,
        compiler: WorkflowCompiler | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.scheduler = scheduler
        self.compiler = compiler or WorkflowCompiler()

    async def create_workflow(
        self,
        data: WorkflowCreate,
        created_by: UUID,
    ) -> WorkflowResponse:
        """Create workflow."""
        existing = await self.repository.get_definition_by_name(
            workspace_id=data.workspace_id,
            name=data.name,
        )
        if existing is not None:
            raise ValidationError(
                "WORKFLOW_NAME_CONFLICT",
                f"Workflow '{data.name}' already exists in this workspace",
            )
        compiled_ir = self.validate_and_compile(data.yaml_source)
        definition = await self.repository.create_definition(
            WorkflowDefinition(
                name=data.name,
                description=data.description,
                status=WorkflowStatus.active,
                schema_version=compiled_ir.schema_version,
                tags=list(data.tags),
                workspace_id=data.workspace_id,
                created_by=created_by,
                updated_by=created_by,
            )
        )
        version = await self.repository.create_version(
            WorkflowVersion(
                definition_id=definition.id,
                version_number=1,
                yaml_source=data.yaml_source,
                compiled_ir=compiled_ir.to_dict(),
                schema_version=compiled_ir.schema_version,
                change_summary=data.change_summary,
                created_by=created_by,
                is_valid=True,
            )
        )
        definition.current_version_id = version.id
        definition.current_version = version
        await self.repository.session.flush()
        await publish_workflow_published(
            self.producer,
            WorkflowPublishedEvent(
                workflow_id=definition.id,
                version_id=version.id,
                version_number=version.version_number,
                workspace_id=definition.workspace_id,
                schema_version=version.schema_version,
            ),
            self._correlation(definition.workspace_id),
        )
        return self._workflow_response(definition)

    async def update_workflow(
        self,
        workflow_id: UUID,
        data: WorkflowUpdate,
        updated_by: UUID,
    ) -> WorkflowResponse:
        """Update workflow."""
        definition = await self._get_definition_or_raise(workflow_id)
        compiled_ir = self.validate_and_compile(data.yaml_source)
        versions = await self.repository.list_versions(workflow_id)
        version = await self.repository.create_version(
            WorkflowVersion(
                definition_id=definition.id,
                version_number=(versions[-1].version_number if versions else 0) + 1,
                yaml_source=data.yaml_source,
                compiled_ir=compiled_ir.to_dict(),
                schema_version=compiled_ir.schema_version,
                change_summary=data.change_summary,
                created_by=updated_by,
                is_valid=True,
            )
        )
        definition.current_version_id = version.id
        definition.current_version = version
        definition.schema_version = compiled_ir.schema_version
        definition.updated_by = updated_by
        await self.repository.session.flush()
        await publish_workflow_published(
            self.producer,
            WorkflowPublishedEvent(
                workflow_id=definition.id,
                version_id=version.id,
                version_number=version.version_number,
                workspace_id=definition.workspace_id,
                schema_version=version.schema_version,
            ),
            self._correlation(definition.workspace_id),
        )
        return self._workflow_response(definition)

    async def archive_workflow(self, workflow_id: UUID, updated_by: UUID) -> WorkflowResponse:
        """Archive workflow."""
        definition = await self._get_definition_or_raise(workflow_id)
        if definition.status == WorkflowStatus.archived:
            raise ValidationError("WORKFLOW_ALREADY_ARCHIVED", "Workflow is already archived")
        definition.status = WorkflowStatus.archived
        definition.updated_by = updated_by
        await self.repository.session.flush()
        return self._workflow_response(definition)

    async def get_workflow(self, workflow_id: UUID) -> WorkflowResponse:
        """Return workflow."""
        return self._workflow_response(await self._get_definition_or_raise(workflow_id))

    async def list_workflows(
        self,
        *,
        workspace_id: UUID,
        status: WorkflowStatus | None,
        tags: list[str] | None,
        page: int,
        page_size: int,
    ) -> WorkflowListResponse:
        """List workflows."""
        items, total = await self.repository.list_definitions(
            workspace_id=workspace_id,
            status=status,
            tags=tags,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return WorkflowListResponse(
            items=[self._workflow_response(item) for item in items],
            total=total,
        )

    async def get_version(self, workflow_id: UUID, version_number: int) -> WorkflowVersionResponse:
        """Return version."""
        version = await self.repository.get_version_by_number(workflow_id, version_number)
        if version is None:
            raise WorkflowNotFoundError(f"{workflow_id}/versions/{version_number}")
        return WorkflowVersionResponse.model_validate(version)

    async def list_versions(self, workflow_id: UUID) -> list[WorkflowVersionResponse]:
        """List versions."""
        await self._get_definition_or_raise(workflow_id)
        versions = await self.repository.list_versions(workflow_id)
        return [WorkflowVersionResponse.model_validate(item) for item in versions]

    async def create_trigger(
        self,
        workflow_id: UUID,
        data: TriggerCreate,
    ) -> TriggerResponse:
        """Create trigger."""
        definition = await self._get_definition_or_raise(workflow_id)
        trigger = await self.repository.create_trigger(
            WorkflowTriggerDefinition(
                definition_id=definition.id,
                trigger_type=data.trigger_type,
                name=data.name,
                is_active=data.is_active,
                config=dict(data.config),
                max_concurrent_executions=data.max_concurrent_executions,
            )
        )
        await self._register_cron_if_needed(trigger)
        return self._trigger_response(trigger)

    async def update_trigger(
        self,
        workflow_id: UUID,
        trigger_id: UUID,
        data: TriggerCreate,
    ) -> TriggerResponse:
        """Update trigger."""
        await self._get_definition_or_raise(workflow_id)
        trigger = await self.repository.get_trigger_by_id(trigger_id)
        if trigger is None or trigger.definition_id != workflow_id:
            raise TriggerNotFoundError(trigger_id)
        await self._remove_cron_if_needed(trigger)
        updated = await self.repository.update_trigger(
            trigger,
            trigger_type=data.trigger_type,
            name=data.name,
            config=dict(data.config),
            max_concurrent_executions=data.max_concurrent_executions,
            is_active=data.is_active,
        )
        await self._register_cron_if_needed(updated)
        return self._trigger_response(updated)

    async def delete_trigger(self, workflow_id: UUID, trigger_id: UUID) -> None:
        """Delete trigger."""
        await self._get_definition_or_raise(workflow_id)
        trigger = await self.repository.get_trigger_by_id(trigger_id)
        if trigger is None or trigger.definition_id != workflow_id:
            raise TriggerNotFoundError(trigger_id)
        await self._remove_cron_if_needed(trigger)
        await self.repository.delete_trigger(trigger)

    async def list_triggers(self, workflow_id: UUID) -> TriggerListResponse:
        """List triggers."""
        await self._get_definition_or_raise(workflow_id)
        items = await self.repository.list_triggers(workflow_id)
        return TriggerListResponse(
            items=[self._trigger_response(item) for item in items],
            total=len(items),
        )

    async def record_trigger_fired(
        self,
        trigger_id: UUID,
        *,
        execution_id: UUID | None,
    ) -> None:
        """Record trigger fired."""
        trigger = await self.repository.get_trigger_by_id(trigger_id)
        if trigger is None:
            raise TriggerNotFoundError(trigger_id)
        trigger.last_fired_at = datetime.now(UTC).replace(tzinfo=None)
        await self.repository.session.flush()
        await publish_trigger_fired(
            self.producer,
            TriggerFiredEvent(
                workflow_id=trigger.definition_id,
                trigger_id=trigger.id,
                trigger_type=trigger.trigger_type.value,
                execution_id=execution_id,
            ),
            self._correlation(execution_id=execution_id),
        )

    def validate_and_compile(self, yaml_source: str) -> WorkflowIR:
        """Validate and compile."""
        return self.compiler.compile(yaml_source, 1)

    async def _get_definition_or_raise(self, workflow_id: UUID) -> WorkflowDefinition:
        definition = await self.repository.get_definition_by_id(workflow_id)
        if definition is None:
            raise WorkflowNotFoundError(workflow_id)
        return definition

    async def _register_cron_if_needed(self, trigger: WorkflowTriggerDefinition) -> None:
        if (
            self.scheduler is None
            or trigger.trigger_type != TriggerType.cron
            or not trigger.is_active
        ):
            return
        cron_expression = trigger.config.get("cron_expression")
        if not cron_expression:
            return
        add_job = getattr(self.scheduler, "add_job", None)
        if callable(add_job):
            add_job(lambda: None, "cron", id=str(trigger.id), replace_existing=True)

    async def _remove_cron_if_needed(self, trigger: WorkflowTriggerDefinition) -> None:
        if self.scheduler is None or trigger.trigger_type != TriggerType.cron:
            return
        remove_job = getattr(self.scheduler, "remove_job", None)
        if callable(remove_job):
            try:
                remove_job(str(trigger.id))
            except Exception:
                return

    @staticmethod
    def _mask_trigger_config(trigger: WorkflowTriggerDefinition) -> dict[str, Any]:
        config = dict(trigger.config)
        if "secret" in config:
            config["secret"] = "***"
        return config

    def _trigger_response(self, trigger: WorkflowTriggerDefinition) -> TriggerResponse:
        return TriggerResponse(
            id=trigger.id,
            trigger_type=trigger.trigger_type,
            name=trigger.name,
            is_active=trigger.is_active,
            config=self._mask_trigger_config(trigger),
            max_concurrent_executions=trigger.max_concurrent_executions,
            last_fired_at=trigger.last_fired_at,
            created_at=trigger.created_at,
            updated_at=trigger.updated_at,
        )

    @staticmethod
    def _workflow_response(definition: WorkflowDefinition) -> WorkflowResponse:
        current_version = (
            WorkflowVersionResponse.model_validate(definition.current_version)
            if definition.current_version is not None
            else None
        )
        return WorkflowResponse(
            id=definition.id,
            name=definition.name,
            description=definition.description,
            status=definition.status,
            schema_version=definition.schema_version,
            tags=list(definition.tags),
            current_version=current_version,
            workspace_id=definition.workspace_id,
            created_at=definition.created_at,
            updated_at=definition.updated_at,
        )

    @staticmethod
    def _correlation(
        workspace_id: UUID | None = None,
        *,
        execution_id: UUID | None = None,
    ) -> CorrelationContext:
        return CorrelationContext(
            workspace_id=workspace_id,
            execution_id=execution_id,
            correlation_id=uuid4(),
        )
