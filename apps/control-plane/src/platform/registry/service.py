from __future__ import annotations

import asyncio
import re
import shutil
from collections.abc import Coroutine
from dataclasses import dataclass
from platform.common import database
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient, PointStruct
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import BucketNotFoundError, ObjectStorageError
from platform.registry.events import (
    AgentCreatedPayload,
    AgentDecommissionedPayload,
    AgentDeprecatedPayload,
    AgentPublishedPayload,
    publish_agent_created,
    publish_agent_decommissioned,
    publish_agent_deprecated,
    publish_agent_published,
)
from platform.registry.exceptions import (
    AgentNotFoundError,
    FQNConflictError,
    InvalidTransitionError,
    InvalidVisibilityPatternError,
    NamespaceConflictError,
    NamespaceNotFoundError,
    RegistryError,
    RegistryStoreUnavailableError,
    RevisionConflictError,
    WorkspaceAuthorizationError,
)
from platform.registry.models import (
    AgentNamespace,
    AgentProfile,
    AgentRevision,
    AssessmentMethod,
    EmbeddingStatus,
    LifecycleAuditEntry,
    LifecycleStatus,
)
from platform.registry.package_validator import PackageValidator
from platform.registry.repository import RegistryRepository
from platform.registry.schemas import (
    AgentDecommissionResponse,
    AgentDiscoveryParams,
    AgentListResponse,
    AgentPatch,
    AgentProfileResponse,
    AgentRevisionResponse,
    AgentUploadResponse,
    LifecycleAuditListResponse,
    LifecycleAuditResponse,
    LifecycleTransitionRequest,
    MaturityUpdateRequest,
    NamespaceCreate,
    NamespaceListResponse,
    NamespaceResponse,
)
from platform.registry.state_machine import (
    EVENT_TRANSITIONS,
    get_valid_transitions,
    is_valid_transition,
)
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy.exc import IntegrityError

_WILDCARD_PATTERN = re.compile(r"^[A-Za-z0-9:_*.-]+$")


@dataclass(frozen=True, slots=True)
class EffectiveVisibility:
    agent_patterns: list[str]
    tool_patterns: list[str]


def build_search_document(
    profile: AgentProfile,
    revision: AgentRevision | None,
) -> dict[str, Any]:
    namespace_name = (
        profile.namespace.name if profile.namespace is not None else profile.fqn.split(":", 1)[0]
    )
    return {
        "agent_profile_id": str(profile.id),
        "fqn": profile.fqn,
        "namespace": namespace_name,
        "local_name": profile.local_name,
        "display_name": profile.display_name,
        "purpose": profile.purpose,
        "approach": profile.approach,
        "tags": list(profile.tags),
        "role_types": list(profile.role_types),
        "maturity_level": profile.maturity_level,
        "status": profile.status.value,
        "workspace_id": str(profile.workspace_id),
        "created_at": profile.created_at.isoformat(),
        "current_revision_id": str(revision.id) if revision is not None else None,
        "current_version": revision.version if revision is not None else None,
    }


def compile_fqn_pattern(pattern: str) -> re.Pattern[str]:
    if _WILDCARD_PATTERN.fullmatch(pattern):
        escaped = re.escape(pattern).replace(r"\*", ".*")
        return re.compile(f"^{escaped}$")
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise InvalidVisibilityPatternError(pattern) from exc


def fqn_matches(pattern: str, fqn: str) -> bool:
    return compile_fqn_pattern(pattern).fullmatch(fqn) is not None


def filter_profiles_by_patterns(
    profiles: list[AgentProfile],
    patterns: list[str],
) -> list[AgentProfile]:
    if not patterns:
        return []
    compiled = [compile_fqn_pattern(pattern) for pattern in patterns]
    return [
        profile
        for profile in profiles
        if any(regex.fullmatch(profile.fqn) is not None for regex in compiled)
    ]


class RegistryService:
    def __init__(
        self,
        *,
        repository: RegistryRepository,
        object_storage: AsyncObjectStorageClient,
        opensearch: AsyncOpenSearchClient,
        qdrant: AsyncQdrantClient,
        workspaces_service: Any | None,
        event_producer: EventProducer | None,
        settings: PlatformSettings,
        package_validator: PackageValidator | None = None,
    ) -> None:
        self.repository = repository
        self.object_storage = object_storage
        self.opensearch = opensearch
        self.qdrant = qdrant
        self.workspaces_service = workspaces_service
        self.event_producer = event_producer
        self.settings = settings
        self.package_validator = package_validator or PackageValidator(settings)
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def create_namespace(
        self,
        workspace_id: UUID,
        params: NamespaceCreate,
        actor_id: UUID,
    ) -> NamespaceResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        existing = await self.repository.get_namespace_by_name(workspace_id, params.name)
        if existing is not None:
            raise NamespaceConflictError(params.name)
        namespace = await self.repository.create_namespace(
            workspace_id=workspace_id,
            name=params.name,
            description=params.description,
            created_by=actor_id,
        )
        await self._commit()
        return self._namespace_response(namespace)

    async def list_namespaces(self, workspace_id: UUID, actor_id: UUID) -> NamespaceListResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        items = await self.repository.list_namespaces(workspace_id)
        return NamespaceListResponse(
            items=[self._namespace_response(namespace) for namespace in items],
            total=len(items),
        )

    async def delete_namespace(
        self,
        workspace_id: UUID,
        namespace_id: UUID,
        actor_id: UUID,
    ) -> None:
        await self._assert_workspace_access(workspace_id, actor_id)
        namespace = await self.repository.get_namespace_by_id(workspace_id, namespace_id)
        if namespace is None:
            raise NamespaceNotFoundError(namespace_id)
        if await self.repository.namespace_has_agents(namespace_id):
            raise RegistryError(
                "REGISTRY_NAMESPACE_NOT_EMPTY",
                "Namespace still has registered agents",
                {"namespace_id": str(namespace_id)},
            )
        await self.repository.delete_namespace(namespace)
        await self._commit()

    async def upload_agent(
        self,
        workspace_id: UUID,
        namespace_name: str,
        package_bytes: bytes,
        filename: str,
        actor_id: UUID,
    ) -> AgentUploadResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        namespace = await self.repository.get_namespace_by_name(workspace_id, namespace_name)
        if namespace is None:
            raise NamespaceNotFoundError(namespace_name)

        validation = await self.package_validator.validate(package_bytes, filename)
        manifest = validation.manifest
        revision_id = uuid4()
        storage_key = (
            f"{workspace_id}/{namespace.name}/{manifest.local_name}/{revision_id}/package.tar.gz"
        )
        bucket = self.settings.registry.package_bucket
        created = False

        try:
            await self.object_storage.create_bucket_if_not_exists(bucket)
            await self.object_storage.upload_object(
                bucket,
                storage_key,
                package_bytes,
                content_type="application/gzip",
            )
        except (BucketNotFoundError, ObjectStorageError) as exc:
            raise RegistryStoreUnavailableError("object_storage", str(exc)) from exc

        try:
            profile, created = await self.repository.upsert_agent_profile(
                workspace_id=workspace_id,
                namespace=namespace,
                local_name=manifest.local_name,
                display_name=manifest.display_name,
                purpose=manifest.purpose,
                approach=manifest.approach,
                role_types=[role.value for role in manifest.role_types],
                custom_role_description=manifest.custom_role_description,
                tags=manifest.tags,
                mcp_server_refs=list(manifest.mcp_servers),
                maturity_level=int(manifest.maturity_level),
                actor_id=actor_id,
            )
            revision = await self.repository.insert_revision(
                revision_id=revision_id,
                workspace_id=workspace_id,
                agent_profile_id=profile.id,
                version=manifest.version,
                sha256_digest=validation.sha256_digest,
                storage_key=storage_key,
                manifest_snapshot=manifest.model_dump(mode="json"),
                uploaded_by=actor_id,
            )
            await self._commit()
        except IntegrityError as exc:
            await self._rollback()
            await self.object_storage.delete_object(bucket, storage_key)
            message = str(exc.orig)
            if "uq_registry_revision_profile_version" in message:
                raise RevisionConflictError(manifest.version) from exc
            if "uq_registry_profile_fqn" in message:
                raise FQNConflictError(f"{namespace.name}:{manifest.local_name}") from exc
            raise
        except Exception:
            await self._rollback()
            await self.object_storage.delete_object(bucket, storage_key)
            raise
        finally:
            shutil.rmtree(validation.temp_dir, ignore_errors=True)

        await self._index_or_flag(profile.id)
        self._dispatch_background_task(self._generate_embedding_async(profile.id))
        await publish_agent_created(
            self.event_producer,
            AgentCreatedPayload(
                agent_profile_id=str(profile.id),
                fqn=profile.fqn,
                namespace=namespace.name,
                workspace_id=str(workspace_id),
                revision_id=str(revision.id),
                version=revision.version,
                maturity_level=profile.maturity_level,
                role_types=list(profile.role_types),
            ),
            self._correlation(workspace_id, profile.fqn),
        )

        return AgentUploadResponse(
            agent_profile=await self._build_profile_response(profile),
            revision=self._revision_response(revision),
            created=created,
        )

    async def get_agent(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        *,
        actor_id: UUID | None = None,
        requesting_agent_id: UUID | None = None,
    ) -> AgentProfileResponse:
        if actor_id is not None:
            await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self.repository.get_agent_by_id(workspace_id, agent_id)
        if profile is None:
            raise AgentNotFoundError(agent_id)
        await self._assert_agent_visible(profile, workspace_id, requesting_agent_id)
        return await self._build_profile_response(profile)

    async def get_agent_by_fqn(
        self,
        fqn: str,
        workspace_id: UUID,
    ) -> AgentProfileResponse | None:
        profile = await self.repository.get_agent_by_fqn(workspace_id, fqn)
        if profile is None or profile.status is LifecycleStatus.archived:
            return None
        return await self._build_profile_response(profile)

    async def resolve_fqn(
        self,
        fqn: str,
        *,
        workspace_id: UUID,
        actor_id: UUID | None = None,
        requesting_agent_id: UUID | None = None,
    ) -> AgentProfileResponse:
        if actor_id is not None:
            await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self.repository.get_by_fqn(workspace_id, fqn)
        if profile is None or profile.status is LifecycleStatus.archived:
            raise AgentNotFoundError(fqn)
        await self._assert_agent_visible(profile, workspace_id, requesting_agent_id)
        return await self._build_profile_response(profile)

    async def list_agents(
        self,
        params: AgentDiscoveryParams,
        *,
        requesting_agent_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> AgentListResponse:
        if params.workspace_id is None:
            raise RegistryError("REGISTRY_WORKSPACE_REQUIRED", "workspace_id is required")
        workspace_id = params.workspace_id
        if actor_id is not None:
            await self._assert_workspace_access(workspace_id, actor_id)

        fetch_limit = max(params.limit + params.offset, 200)
        if params.keyword:
            visibility_filter = None
            if requesting_agent_id is not None and self.settings.visibility.zero_trust_enabled:
                visibility_filter = await self.resolve_effective_visibility(
                    requesting_agent_id,
                    workspace_id,
                )
            agent_ids, _ = await self.repository.search_by_keyword(
                workspace_id=workspace_id,
                keyword=params.keyword,
                status=params.status,
                maturity_min=params.maturity_min,
                limit=fetch_limit,
                offset=0,
                index_name=self.settings.registry.search_index,
            )
            profiles = await self.repository.get_agents_by_ids(
                workspace_id,
                agent_ids,
                visibility_filter=visibility_filter,
            )
            visible_profiles = profiles
        else:
            visibility_filter = None
            if requesting_agent_id is not None and self.settings.visibility.zero_trust_enabled:
                visibility_filter = await self.resolve_effective_visibility(
                    requesting_agent_id,
                    workspace_id,
                )
            visible_profiles, total = await self.repository.list_agents_by_workspace(
                workspace_id,
                status=params.status,
                maturity_min=params.maturity_min,
                limit=fetch_limit,
                offset=0,
                visibility_filter=visibility_filter,
                include_decommissioned=False,
            )
            del total

        if params.fqn_pattern:
            visible_profiles = [
                profile
                for profile in visible_profiles
                if fqn_matches(params.fqn_pattern, profile.fqn)
            ]

        paginated = visible_profiles[params.offset : params.offset + params.limit]
        items = [await self._build_profile_response(profile) for profile in paginated]
        return AgentListResponse(
            items=items,
            total=len(visible_profiles),
            limit=params.limit,
            offset=params.offset,
        )

    async def patch_agent(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        patch: AgentPatch,
        actor_id: UUID,
    ) -> AgentProfileResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self._get_agent_or_raise(workspace_id, agent_id)
        updates: dict[str, Any] = {}
        if "display_name" in patch.model_fields_set:
            updates["display_name"] = patch.display_name
        if "approach" in patch.model_fields_set:
            updates["approach"] = patch.approach
        if "tags" in patch.model_fields_set and patch.tags is not None:
            updates["tags"] = patch.tags
        if "visibility_agents" in patch.model_fields_set and patch.visibility_agents is not None:
            self._validate_patterns(patch.visibility_agents)
            updates["visibility_agents"] = patch.visibility_agents
        if "visibility_tools" in patch.model_fields_set and patch.visibility_tools is not None:
            self._validate_patterns(patch.visibility_tools)
            updates["visibility_tools"] = patch.visibility_tools
        if "role_types" in patch.model_fields_set and patch.role_types is not None:
            updates["role_types"] = [role.value for role in patch.role_types]
        if "custom_role_description" in patch.model_fields_set:
            updates["custom_role_description"] = patch.custom_role_description
        if "mcp_servers" in patch.model_fields_set and patch.mcp_servers is not None:
            updates["mcp_server_refs"] = patch.mcp_servers

        if updates:
            await self.repository.update_agent_profile(profile, **updates)
            await self._commit()
            await self._index_or_flag(profile.id)
        return await self._build_profile_response(profile)

    async def transition_lifecycle(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        request: LifecycleTransitionRequest,
        actor_id: UUID,
    ) -> AgentProfileResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self._get_agent_or_raise(workspace_id, agent_id)
        if profile.status is LifecycleStatus.decommissioned:
            raise InvalidTransitionError(
                profile.status.value,
                request.target_status.value,
                sorted(status.value for status in get_valid_transitions(profile.status)),
            )
        if not is_valid_transition(profile.status, request.target_status):
            raise InvalidTransitionError(
                profile.status.value,
                request.target_status.value,
                sorted(status.value for status in get_valid_transitions(profile.status)),
            )
        previous_status = profile.status
        profile.status = request.target_status
        await self.repository.insert_lifecycle_audit(
            workspace_id=workspace_id,
            agent_profile_id=profile.id,
            previous_status=previous_status,
            new_status=request.target_status,
            actor_id=actor_id,
            reason=request.reason,
        )
        await self._commit()
        await self._index_or_flag(profile.id)

        correlation = self._correlation(workspace_id, profile.fqn)
        if request.target_status in EVENT_TRANSITIONS:
            if request.target_status is LifecycleStatus.published:
                await publish_agent_published(
                    self.event_producer,
                    AgentPublishedPayload(
                        agent_profile_id=str(profile.id),
                        fqn=profile.fqn,
                        workspace_id=str(profile.workspace_id),
                        published_by=str(actor_id),
                    ),
                    correlation,
                )
            if request.target_status is LifecycleStatus.deprecated:
                await publish_agent_deprecated(
                    self.event_producer,
                    AgentDeprecatedPayload(
                        agent_profile_id=str(profile.id),
                        fqn=profile.fqn,
                        workspace_id=str(profile.workspace_id),
                        deprecated_by=str(actor_id),
                        reason=request.reason,
                    ),
                    correlation,
                )
        return await self._build_profile_response(profile)

    async def decommission_agent(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        reason: str,
        actor_id: UUID,
        runtime_controller: Any | None,
        *,
        actor_is_platform_admin: bool = False,
    ) -> AgentDecommissionResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        await self._assert_decommission_permission(
            workspace_id,
            actor_id,
            actor_is_platform_admin=actor_is_platform_admin,
        )
        normalized_reason = reason.strip()
        if len(normalized_reason) < 10 or len(normalized_reason) > 2000:
            raise RegistryError(
                "REGISTRY_DECOMMISSION_REASON_INVALID",
                "Decommission reason must be between 10 and 2000 characters",
                {"min_length": 10, "max_length": 2000},
            )
        profile = await self._get_agent_or_raise(workspace_id, agent_id)
        if profile.status is LifecycleStatus.decommissioned:
            return AgentDecommissionResponse(
                agent_id=profile.id,
                agent_fqn=profile.fqn,
                decommissioned_at=profile.decommissioned_at or profile.updated_at,
                decommission_reason=profile.decommission_reason or normalized_reason,
                decommissioned_by=profile.decommissioned_by or actor_id,
                active_instances_stopped=0,
            )

        active_instances = await self._list_active_instances(runtime_controller, profile.fqn)
        await asyncio.gather(
            *(
                self._stop_runtime(runtime_controller, execution_id)
                for execution_id in active_instances
            )
        )
        previous_status = profile.status
        profile = await self.repository.persist_decommission(
            profile,
            reason=normalized_reason,
            actor_id=actor_id,
        )
        await self.repository.insert_lifecycle_audit(
            workspace_id=workspace_id,
            agent_profile_id=profile.id,
            previous_status=previous_status,
            new_status=LifecycleStatus.decommissioned,
            actor_id=actor_id,
            reason=normalized_reason,
        )
        await self._commit()
        await self._index_or_flag(profile.id)
        await publish_agent_decommissioned(
            self.event_producer,
            AgentDecommissionedPayload(
                agent_profile_id=str(profile.id),
                fqn=profile.fqn,
                decommissioned_by=str(actor_id),
                decommissioned_at=(profile.decommissioned_at or profile.updated_at).isoformat(),
                reason=normalized_reason,
                active_instance_count_at_decommission=len(active_instances),
            ),
            self._correlation(workspace_id, profile.fqn),
        )
        return AgentDecommissionResponse(
            agent_id=profile.id,
            agent_fqn=profile.fqn,
            decommissioned_at=profile.decommissioned_at or profile.updated_at,
            decommission_reason=profile.decommission_reason or normalized_reason,
            decommissioned_by=profile.decommissioned_by or actor_id,
            active_instances_stopped=len(active_instances),
        )

    async def list_lifecycle_audit(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        actor_id: UUID,
    ) -> LifecycleAuditListResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self._get_agent_or_raise(workspace_id, agent_id)
        entries = await self.repository.list_lifecycle_audit(profile.id)
        return LifecycleAuditListResponse(
            items=[self._audit_response(entry) for entry in entries],
            total=len(entries),
        )

    async def update_maturity(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        request: MaturityUpdateRequest,
        actor_id: UUID,
    ) -> AgentProfileResponse:
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self._get_agent_or_raise(workspace_id, agent_id)
        previous_level = int(profile.maturity_level)
        new_level = int(request.maturity_level)
        if previous_level != new_level:
            profile.maturity_level = new_level
            await self.repository.insert_maturity_record(
                workspace_id=workspace_id,
                agent_profile_id=profile.id,
                previous_level=previous_level,
                new_level=new_level,
                assessment_method=AssessmentMethod.system_assessed,
                reason=request.reason,
                actor_id=actor_id,
            )
            await self._commit()
            await self._index_or_flag(profile.id)
        return await self._build_profile_response(profile)

    async def list_revisions(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        actor_id: UUID,
    ) -> list[AgentRevisionResponse]:
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self._get_agent_or_raise(workspace_id, agent_id)
        return [
            self._revision_response(revision)
            for revision in await self.repository.list_revisions(profile.id)
        ]

    async def resolve_effective_visibility(
        self,
        agent_id: UUID,
        workspace_id: UUID,
    ) -> EffectiveVisibility:
        profile = await self._get_agent_or_raise(workspace_id, agent_id)
        workspace_visibility = await self._get_workspace_visibility(workspace_id)
        patterns = list(profile.visibility_agents) + list(workspace_visibility.agent_patterns)
        tool_patterns = list(profile.visibility_tools) + list(workspace_visibility.tool_patterns)
        self._validate_patterns(patterns)
        self._validate_patterns(tool_patterns)
        return EffectiveVisibility(
            agent_patterns=self._dedupe(patterns),
            tool_patterns=self._dedupe(tool_patterns),
        )

    async def get_agent_namespace_owner(self, agent_id: UUID) -> UUID | None:
        profile = await self.repository.get_agent_by_id_any(agent_id)
        if profile is None:
            return None
        return profile.namespace.created_by

    async def _get_workspace_visibility(self, workspace_id: UUID) -> EffectiveVisibility:
        if self.workspaces_service is None:
            return EffectiveVisibility([], [])
        getter = getattr(self.workspaces_service, "get_workspace_visibility_grant", None)
        if getter is None:
            getter = getattr(self.workspaces_service, "get_visibility_grant", None)
        if getter is None:
            return EffectiveVisibility([], [])
        response = await getter(workspace_id)
        if response is None:
            return EffectiveVisibility([], [])
        return EffectiveVisibility(
            agent_patterns=list(getattr(response, "visibility_agents", [])),
            tool_patterns=list(getattr(response, "visibility_tools", [])),
        )

    async def _build_profile_response(self, profile: AgentProfile) -> AgentProfileResponse:
        current_revision = await self.repository.get_latest_revision(profile.id)
        return AgentProfileResponse(
            id=profile.id,
            namespace_id=profile.namespace_id,
            fqn=profile.fqn,
            display_name=profile.display_name,
            purpose=profile.purpose,
            approach=profile.approach,
            role_types=list(profile.role_types),
            custom_role_description=profile.custom_role_description,
            visibility_agents=list(profile.visibility_agents),
            visibility_tools=list(profile.visibility_tools),
            tags=list(profile.tags),
            mcp_servers=list(profile.mcp_server_refs or []),
            status=profile.status,
            maturity_level=int(profile.maturity_level),
            embedding_status=profile.embedding_status,
            workspace_id=profile.workspace_id,
            created_at=profile.created_at,
            current_revision=(
                self._revision_response(current_revision) if current_revision is not None else None
            ),
        )

    def _namespace_response(self, namespace: AgentNamespace) -> NamespaceResponse:
        return NamespaceResponse(
            id=namespace.id,
            name=namespace.name,
            description=namespace.description,
            workspace_id=namespace.workspace_id,
            created_at=namespace.created_at,
            created_by=namespace.created_by,
        )

    def _revision_response(self, revision: AgentRevision) -> AgentRevisionResponse:
        return AgentRevisionResponse(
            id=revision.id,
            agent_profile_id=revision.agent_profile_id,
            version=revision.version,
            sha256_digest=revision.sha256_digest,
            storage_key=revision.storage_key,
            manifest_snapshot=dict(revision.manifest_snapshot),
            uploaded_by=revision.uploaded_by,
            created_at=revision.created_at,
        )

    def _audit_response(self, entry: LifecycleAuditEntry) -> LifecycleAuditResponse:
        return LifecycleAuditResponse(
            id=entry.id,
            agent_profile_id=entry.agent_profile_id,
            previous_status=entry.previous_status,
            new_status=entry.new_status,
            actor_id=entry.actor_id,
            reason=entry.reason,
            created_at=entry.created_at,
        )

    async def _assert_decommission_permission(
        self,
        workspace_id: UUID,
        actor_id: UUID,
        *,
        actor_is_platform_admin: bool = False,
    ) -> None:
        if actor_is_platform_admin:
            return
        membership = None
        repo = getattr(self.workspaces_service, "repo", None)
        repo_get_membership = getattr(repo, "get_membership", None)
        service_get_membership = getattr(self.workspaces_service, "get_membership", None)
        if callable(repo_get_membership):
            membership = await repo_get_membership(workspace_id, actor_id)
        elif callable(service_get_membership):
            membership = await service_get_membership(workspace_id, actor_id)
        role = getattr(membership, "role", None)
        if str(role) not in {"owner", "WorkspaceRole.owner"}:
            raise WorkspaceAuthorizationError(workspace_id)

    async def _list_active_instances(
        self,
        runtime_controller: Any | None,
        agent_fqn: str,
    ) -> list[str]:
        if runtime_controller is None:
            return []
        getter = getattr(runtime_controller, "list_active_instances", None)
        if getter is None:
            return []
        result = getter(agent_fqn)
        if hasattr(result, "__await__"):
            result = await result
        return [str(item) for item in (result or [])]

    async def _stop_runtime(self, runtime_controller: Any | None, execution_id: str) -> None:
        if runtime_controller is None:
            return
        stopper = getattr(runtime_controller, "stop_runtime", None)
        if stopper is None:
            return
        result = stopper(execution_id)
        if hasattr(result, "__await__"):
            await result

    async def _assert_workspace_access(self, workspace_id: UUID, actor_id: UUID) -> None:
        if self.workspaces_service is None:
            raise WorkspaceAuthorizationError(workspace_id)
        workspace_ids = await self.workspaces_service.get_user_workspace_ids(actor_id)
        if workspace_id not in set(workspace_ids):
            raise WorkspaceAuthorizationError(workspace_id)

    async def _get_agent_or_raise(self, workspace_id: UUID, agent_id: UUID) -> AgentProfile:
        profile = await self.repository.get_agent_by_id(workspace_id, agent_id)
        if profile is None:
            raise AgentNotFoundError(agent_id)
        return profile

    async def _assert_agent_visible(
        self,
        profile: AgentProfile,
        workspace_id: UUID,
        requesting_agent_id: UUID | None,
    ) -> None:
        if requesting_agent_id is None or not self.settings.visibility.zero_trust_enabled:
            return
        effective_visibility = await self.resolve_effective_visibility(
            requesting_agent_id,
            workspace_id,
        )
        if any(
            fqn_matches(pattern, profile.fqn) for pattern in effective_visibility.agent_patterns
        ):
            return
        await self._publish_visibility_denied(
            profile=profile,
            workspace_id=workspace_id,
            requesting_agent_id=requesting_agent_id,
        )
        raise AgentNotFoundError(profile.id)

    async def _publish_visibility_denied(
        self,
        *,
        profile: AgentProfile,
        workspace_id: UUID,
        requesting_agent_id: UUID,
    ) -> None:
        if self.event_producer is None:
            return
        await self.event_producer.publish(
            topic="registry.events",
            key=str(profile.id),
            event_type="registry.agent.visibility_denied",
            payload={
                "agent_profile_id": str(profile.id),
                "fqn": profile.fqn,
                "workspace_id": str(profile.workspace_id),
                "requesting_agent_id": str(requesting_agent_id),
                "block_reason": "visibility_denied",
            },
            correlation_ctx=self._correlation(workspace_id, profile.fqn),
            source="platform.registry",
        )

    def _validate_patterns(self, patterns: list[str]) -> None:
        for pattern in patterns:
            compile_fqn_pattern(pattern)

    def _dispatch_background_task(
        self,
        coroutine: Coroutine[Any, Any, None],
    ) -> None:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _index_or_flag(self, agent_profile_id: UUID) -> None:
        raw_profile = await self.repository.session.get(AgentProfile, agent_profile_id)
        if raw_profile is None:
            return
        profile = await self.repository.get_agent_by_id(raw_profile.workspace_id, agent_profile_id)
        if profile is None:
            return
        revision = await self.repository.get_latest_revision(profile.id)
        try:
            await self.opensearch.index_document(
                self.settings.registry.search_index,
                build_search_document(profile, revision),
                document_id=str(profile.id),
                refresh=False,
            )
            await self.repository.set_needs_reindex(profile.id, False)
            await self._commit()
        except Exception:
            await self.repository.set_needs_reindex(profile.id, True)
            await self._commit()

    async def _generate_embedding_async(self, agent_profile_id: UUID) -> None:
        async with database.AsyncSessionLocal() as session:
            repository = RegistryRepository(session, self.opensearch)
            profile = await session.get(AgentProfile, agent_profile_id)
            if profile is None:
                return
            text = " ".join(part for part in [profile.purpose, profile.approach] if part)
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        self.settings.registry.embedding_api_url,
                        json={"input": text},
                    )
                    response.raise_for_status()
                    data = response.json()
                    embedding = self._extract_embedding(data)
                await self.qdrant.upsert_vectors(
                    self.settings.registry.embeddings_collection,
                    [
                        PointStruct(
                            id=str(profile.id),
                            vector=embedding,
                            payload={
                                "fqn": profile.fqn,
                                "workspace_id": str(profile.workspace_id),
                                "namespace": profile.fqn.split(":", 1)[0],
                                "status": profile.status.value,
                            },
                        )
                    ],
                )
                await repository.set_embedding_status(profile.id, EmbeddingStatus.complete)
                await session.commit()
            except Exception:
                await repository.set_embedding_status(profile.id, EmbeddingStatus.failed)
                await session.commit()

    def _extract_embedding(self, payload: dict[str, Any]) -> list[float]:
        if isinstance(payload.get("embedding"), list):
            return [float(item) for item in payload["embedding"]]
        data = payload.get("data")
        if (
            isinstance(data, list)
            and data
            and isinstance(data[0], dict)
            and isinstance(data[0].get("embedding"), list)
        ):
            return [float(item) for item in data[0]["embedding"]]
        raise RegistryStoreUnavailableError("embedding_api", "Embedding response missing vector")

    async def _commit(self) -> None:
        if hasattr(self.repository.session, "commit"):
            await self.repository.session.commit()

    async def _rollback(self) -> None:
        if hasattr(self.repository.session, "rollback"):
            await self.repository.session.rollback()

    def _correlation(self, workspace_id: UUID, agent_fqn: str | None = None) -> CorrelationContext:
        return CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
        )

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered
