from __future__ import annotations

import asyncio
import re
import shutil
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from platform.billing.quotas.http import raise_for_quota_result
from platform.common import database
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient, PointStruct
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import BucketNotFoundError, ObjectStorageError, ValidationError
from platform.common.logging import get_logger
from platform.common.tagging.filter_extension import TagLabelFilterParams
from platform.common.tagging.listing import resolve_filtered_entity_ids
from platform.common.tenant_context import get_current_tenant
from platform.marketplace.metrics import (
    marketplace_forks_total,
    marketplace_submissions_total,
)
from platform.model_catalog.models import ModelCatalogEntry
from platform.model_catalog.repository import ModelCatalogRepository
from platform.privacy_compliance.services.pia_service import DATA_CATEGORIES_REQUIRING_PIA
from platform.registry.events import (
    AgentCreatedPayload,
    AgentDecommissionedPayload,
    AgentDeprecatedPayload,
    AgentPublishedPayload,
    MarketplaceDeprecatedPayload,
    MarketplaceEventType,
    MarketplaceForkedPayload,
    MarketplacePublishedPayload,
    MarketplaceScopeChangedPayload,
    MarketplaceSubmittedPayload,
    publish_agent_created,
    publish_agent_decommissioned,
    publish_agent_deprecated,
    publish_agent_published,
    publish_marketplace_event,
)
from platform.registry.exceptions import (
    AgentNotFoundError,
    FQNConflictError,
    InvalidTransitionError,
    InvalidVisibilityPatternError,
    MarketingMetadataRequiredError,
    NamespaceConflictError,
    NamespaceNotFoundError,
    NameTakenInTargetNamespaceError,
    PublicScopeNotAllowedForEnterpriseError,
    RegistryError,
    RegistryStoreUnavailableError,
    RevisionConflictError,
    SourceAgentNotVisibleError,
    SubmissionAlreadyResolvedError,
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
    DeprecateListingRequest,
    ForkAgentRequest,
    ForkAgentResponse,
    LifecycleAuditListResponse,
    LifecycleAuditResponse,
    LifecycleTransitionRequest,
    MarketplaceScopeChangeRequest,
    MaturityUpdateRequest,
    NamespaceCreate,
    NamespaceListResponse,
    NamespaceResponse,
    PublishWithScopeRequest,
)
from platform.registry.state_machine import (
    EVENT_TRANSITIONS,
    get_valid_transitions,
    is_valid_review_transition,
    is_valid_transition,
)
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy.exc import IntegrityError

_WILDCARD_PATTERN = re.compile(r"^[A-Za-z0-9:_*.-]+$")
LOGGER = get_logger(__name__)


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
        "data_categories": list(getattr(profile, "data_categories", []) or []),
        "maturity_level": profile.maturity_level,
        "status": profile.status.value,
        "workspace_id": str(profile.workspace_id),
        "created_at": profile.created_at.isoformat(),
        "current_revision_id": str(revision.id) if revision is not None else None,
        "current_version": revision.version if revision is not None else None,
        # UPD-049: include scope and review status in the search document
        # so the marketplace UI can render scope-aware labels and so the
        # platform-staff review-queue API can find pending rows quickly.
        "marketplace_scope": getattr(profile, "marketplace_scope", "workspace"),
        "review_status": getattr(profile, "review_status", "draft"),
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


def _marketing_description_hash(description: str) -> str:
    """SHA-256 of the marketing description, prefixed ``sha256-`` per the
    Kafka envelope contract (see contracts/marketplace-events-kafka.md).

    Used in the ``marketplace.submitted`` event payload to prove
    description integrity without putting the full text on the bus.
    """
    return "sha256-" + sha256(description.encode("utf-8")).hexdigest()


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
        model_catalog_repository: ModelCatalogRepository | None = None,
        pia_service: Any | None = None,
        package_validator: PackageValidator | None = None,
        tag_service: Any | None = None,
        label_service: Any | None = None,
        tagging_service: Any | None = None,
        quota_enforcer: Any | None = None,
    ) -> None:
        self.repository = repository
        self.object_storage = object_storage
        self.opensearch = opensearch
        self.qdrant = qdrant
        self.model_catalog_repository = model_catalog_repository
        self.workspaces_service = workspaces_service
        self.event_producer = event_producer
        self.settings = settings
        self.pia_service = pia_service
        self.package_validator = package_validator or PackageValidator(settings)
        self.tag_service = tag_service
        self.label_service = label_service
        self.tagging_service = tagging_service
        self.quota_enforcer = quota_enforcer
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
        namespace_name = namespace.name
        storage_key = (
            f"{workspace_id}/{namespace_name}/{manifest.local_name}/{revision_id}/package.tar.gz"
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
            existing_profile = await self.repository.get_agent_by_fqn(
                workspace_id,
                f"{namespace_name}:{manifest.local_name}",
            )
            old_data_categories = self._normalized_categories(
                getattr(existing_profile, "data_categories", []) if existing_profile else []
            )
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
                data_categories=manifest.data_categories,
                maturity_level=int(manifest.maturity_level),
                actor_id=actor_id,
            )
            if not created:
                await self._check_pia_material_change(
                    profile,
                    old_data_categories,
                    manifest.data_categories,
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
                raise FQNConflictError(f"{namespace_name}:{manifest.local_name}") from exc
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
                namespace=namespace_name,
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
        visibility_filter = None
        if requesting_agent_id is not None and self.settings.visibility.zero_trust_enabled:
            visibility_filter = await self.resolve_effective_visibility(
                requesting_agent_id,
                workspace_id,
            )

        tag_label_filters = TagLabelFilterParams(tags=params.tags, labels=params.labels)
        allowed_ids = None
        if tag_label_filters.tags or tag_label_filters.labels:
            visible_for_tagging, _ = await self.repository.list_agents_by_workspace(
                workspace_id,
                status=params.status,
                maturity_min=params.maturity_min,
                limit=10_000,
                offset=0,
                visibility_filter=visibility_filter,
                include_decommissioned=False,
            )
            if params.fqn_pattern:
                visible_for_tagging = [
                    profile
                    for profile in visible_for_tagging
                    if fqn_matches(params.fqn_pattern, profile.fqn)
                ]
            allowed_ids = await resolve_filtered_entity_ids(
                entity_type="agent",
                visible_entity_ids={profile.id for profile in visible_for_tagging},
                filters=tag_label_filters,
                tag_service=self.tag_service,
                label_service=self.label_service,
            )

        if params.keyword:
            agent_ids, _ = await self.repository.search_by_keyword(
                workspace_id=workspace_id,
                keyword=params.keyword,
                status=params.status,
                maturity_min=params.maturity_min,
                limit=fetch_limit,
                offset=0,
                index_name=self.settings.registry.search_index,
            )
            visible_profiles = await self.repository.get_agents_by_ids(
                workspace_id,
                agent_ids,
                visibility_filter=visibility_filter,
            )
            if allowed_ids is not None:
                visible_profiles = [
                    profile for profile in visible_profiles if profile.id in allowed_ids
                ]
            if not visible_profiles:
                visible_profiles = await self._search_profiles_by_keyword_fallback(
                    workspace_id=workspace_id,
                    keyword=params.keyword,
                    status=params.status,
                    maturity_min=params.maturity_min,
                    limit=fetch_limit,
                    visibility_filter=visibility_filter,
                )
                if allowed_ids is not None:
                    visible_profiles = [
                        profile for profile in visible_profiles if profile.id in allowed_ids
                    ]
        else:
            visible_profiles, total = await self.repository.list_agents_by_workspace(
                workspace_id,
                status=params.status,
                maturity_min=params.maturity_min,
                limit=fetch_limit,
                offset=0,
                visibility_filter=visibility_filter,
                include_decommissioned=False,
                allowed_ids=allowed_ids,
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

    async def _search_profiles_by_keyword_fallback(
        self,
        *,
        workspace_id: UUID,
        keyword: str,
        status: LifecycleStatus | None,
        maturity_min: int,
        limit: int,
        visibility_filter: EffectiveVisibility | None,
    ) -> list[AgentProfile]:
        fallback_limit = max(limit, 500)
        profiles, _ = await self.repository.list_agents_by_workspace(
            workspace_id,
            status=status,
            maturity_min=maturity_min,
            limit=fallback_limit,
            offset=0,
            visibility_filter=visibility_filter,
            include_decommissioned=False,
        )
        scored_profiles: list[tuple[int, AgentProfile]] = []
        for profile in profiles:
            score = self._keyword_match_score(profile, keyword)
            if score > 0:
                scored_profiles.append((score, profile))
        scored_profiles.sort(
            key=lambda item: (-item[0], item[1].created_at, str(item[1].id))
        )
        return [profile for _, profile in scored_profiles[:limit]]

    def _keyword_match_score(self, profile: AgentProfile, keyword: str) -> int:
        terms = self._keyword_terms(keyword)
        if not terms:
            return 0

        namespace_name = (
            profile.namespace.name
            if profile.namespace is not None
            else profile.fqn.split(":", 1)[0]
        )
        full_query = " ".join(terms)
        weighted_fields = (
            (profile.display_name, 6),
            (profile.fqn, 5),
            (profile.local_name, 4),
            (namespace_name, 3),
            (profile.purpose, 5),
            (profile.approach, 3),
            (profile.custom_role_description, 2),
            (" ".join(profile.tags), 3),
            (" ".join(profile.role_types), 2),
            (" ".join(getattr(profile, "data_categories", []) or []), 3),
        )
        score = 0
        for value, weight in weighted_fields:
            if not value:
                continue
            normalized_value = self._normalize_keyword_text(value)
            if full_query in normalized_value:
                score += weight * (len(terms) + 1)
            score += sum(weight for term in terms if term in normalized_value)
        return score

    def _keyword_terms(self, keyword: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", keyword.casefold())

    def _normalize_keyword_text(self, value: str) -> str:
        return " ".join(self._keyword_terms(value))

    async def _validate_model_binding(self, profile: AgentProfile, binding: str | None) -> None:
        if not binding or self.model_catalog_repository is None:
            return

        provider, separator, model_id = binding.partition(":")
        if not separator or not provider or not model_id:
            alternatives = await self._model_binding_alternatives(profile)
            raise ValidationError(
                "MODEL_BINDING_INVALID",
                "Model binding must be formatted as provider:model_id.",
                {"binding": binding, "alternatives": alternatives},
            )

        entry = await self.model_catalog_repository.get_entry_by_provider_model(
            provider,
            model_id,
        )
        if entry is not None and entry.status != "blocked":
            return

        alternatives = await self._model_binding_alternatives(profile, entry)
        code = "MODEL_BINDING_BLOCKED" if entry is not None else "MODEL_BINDING_NOT_FOUND"
        reason = "blocked" if entry is not None else "not present in the approved catalogue"
        raise ValidationError(
            code,
            f"Model binding {binding!r} is {reason}.",
            {"binding": binding, "alternatives": alternatives},
        )

    async def _model_binding_alternatives(
        self,
        profile: AgentProfile,
        target_entry: ModelCatalogEntry | None = None,
    ) -> list[dict[str, str]]:
        if self.model_catalog_repository is None:
            return []

        purpose_text = " ".join(
            value
            for value in (
                profile.purpose,
                profile.approach or "",
                " ".join(profile.tags),
                " ".join(profile.role_types),
            )
            if value
        )
        terms = set(self._keyword_terms(purpose_text))
        target_tier = target_entry.quality_tier if target_entry is not None else None
        entries = await self.model_catalog_repository.list_entries(status="approved")

        scored: list[tuple[int, str, ModelCatalogEntry]] = []
        for entry in entries:
            entry_terms = self._normalize_keyword_text(
                " ".join(
                    str(value)
                    for value in (
                        entry.provider,
                        entry.model_id,
                        entry.display_name or "",
                        entry.quality_tier,
                        " ".join(entry.approved_use_cases or []),
                    )
                    if value
                )
            )
            score = sum(3 for term in terms if term in entry_terms)
            if target_tier is not None and entry.quality_tier == target_tier:
                score += 2
            scored.append((score, f"{entry.provider}:{entry.model_id}", entry))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            {
                "binding": binding,
                "quality_tier": entry.quality_tier,
                "provider": entry.provider,
            }
            for _score, binding, entry in scored[:3]
        ]

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
        if "purpose" in patch.model_fields_set and patch.purpose is not None:
            updates["purpose"] = patch.purpose
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
        old_data_categories = self._normalized_categories(
            getattr(profile, "data_categories", []) or []
        )
        if "data_categories" in patch.model_fields_set and patch.data_categories is not None:
            updates["data_categories"] = patch.data_categories
        if "default_model_binding" in patch.model_fields_set:
            await self._validate_model_binding(profile, patch.default_model_binding)
            updates["default_model_binding"] = patch.default_model_binding

        if updates:
            await self.repository.update_agent_profile(profile, **updates)
            if "data_categories" in updates:
                await self._check_pia_material_change(
                    profile,
                    old_data_categories,
                    updates["data_categories"],
                )
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
        if (
            self.quota_enforcer is not None
            and request.target_status is LifecycleStatus.published
            and profile.status is not LifecycleStatus.published
        ):
            quota_result = await self.quota_enforcer.check_agent_publish(workspace_id)
            raise_for_quota_result(quota_result, workspace_id=workspace_id)
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

    # ---------------------------------------------------------------------
    # UPD-049 — public-marketplace publish, scope change, deprecate listing.
    # The legacy /transition path stays compatible (rule 7); the new methods
    # below are called by the new /publish, /marketplace-scope, and
    # /deprecate-listing endpoints.
    # ---------------------------------------------------------------------

    async def publish_with_scope(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        request: PublishWithScopeRequest,
        actor_id: UUID,
        rate_limiter: Any | None = None,
    ) -> AgentProfileResponse:
        """Publish an agent at the chosen marketplace scope.

        For ``workspace`` / ``tenant`` scope: transitions ``review_status``
        to ``published`` directly and emits ``marketplace.published``.

        For ``public_default_tenant`` scope: enforces the three-layer
        Enterprise refusal (FR-010/011/012) — service-layer guard runs
        BEFORE consuming a rate-limit token or writing audit/Kafka so
        a refusal does not consume budget. On success, transitions
        ``review_status`` to ``pending_review`` and emits
        ``marketplace.submitted``.
        """
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self._get_agent_or_raise(workspace_id, agent_id)
        target_scope = request.scope
        previous_scope = profile.marketplace_scope
        previous_review_status = profile.review_status

        if target_scope == "public_default_tenant":
            tenant = get_current_tenant()
            if tenant.kind != "default":
                # FR-011 — service-layer leg of three-layer refusal. Raises
                # before any side effects so we don't consume a rate-limit
                # token or write an audit entry for a refused submission.
                raise PublicScopeNotAllowedForEnterpriseError(tenant.slug)
            if request.marketing_metadata is None:
                # Defensive — the Pydantic validator already enforces this,
                # but the service guard makes the contract testable
                # without going through HTTP.
                raise MarketingMetadataRequiredError()
            if rate_limiter is not None:
                await rate_limiter.check_and_record(actor_id)

            profile.marketplace_scope = target_scope
            profile.review_status = "pending_review"
            await self.repository.insert_lifecycle_audit(
                workspace_id=workspace_id,
                agent_profile_id=profile.id,
                previous_status=profile.status,
                new_status=profile.status,  # lifecycle status unchanged here
                actor_id=actor_id,
                reason=(
                    f"marketplace_submit: scope={previous_scope}->{target_scope} "
                    f"review_status={previous_review_status}->pending_review"
                ),
            )
            await self._commit()
            await self._index_or_flag(profile.id)
            await publish_marketplace_event(
                self.event_producer,
                MarketplaceEventType.submitted,
                MarketplaceSubmittedPayload(
                    agent_id=str(profile.id),
                    submitter_user_id=str(actor_id),
                    category=request.marketing_metadata.category,
                    tags=list(request.marketing_metadata.tags),
                    marketing_description_hash=_marketing_description_hash(
                        request.marketing_metadata.marketing_description
                    ),
                ),
                self._correlation(workspace_id, profile.fqn),
            )
            marketplace_submissions_total.labels(
                category=request.marketing_metadata.category
            ).inc()
            LOGGER.info(
                "marketplace.public_submission",
                extra={
                    "agent_id": str(profile.id),
                    "agent_fqn": profile.fqn,
                    "marketplace_scope": target_scope,
                    "review_status": "pending_review",
                    "actor_user_id": str(actor_id),
                    "tenant_id": str(profile.tenant_id),
                    "category": request.marketing_metadata.category,
                },
            )
            if previous_scope != target_scope:
                await publish_marketplace_event(
                    self.event_producer,
                    MarketplaceEventType.scope_changed,
                    MarketplaceScopeChangedPayload(
                        agent_id=str(profile.id),
                        from_scope=previous_scope,
                        to_scope=target_scope,
                        actor_user_id=str(actor_id),
                    ),
                    self._correlation(workspace_id, profile.fqn),
                )
            return await self._build_profile_response(profile)

        # workspace / tenant scope: direct publish, no review.
        profile.marketplace_scope = target_scope
        profile.review_status = "published"
        # Keep the lifecycle status path symmetric with /transition for
        # backward compatibility — if the agent isn't already published in
        # the lifecycle sense, advance it.
        if profile.status is LifecycleStatus.validated:
            profile.status = LifecycleStatus.published
        await self.repository.insert_lifecycle_audit(
            workspace_id=workspace_id,
            agent_profile_id=profile.id,
            previous_status=profile.status,
            new_status=profile.status,
            actor_id=actor_id,
            reason=(
                f"marketplace_publish: scope={previous_scope}->{target_scope} "
                f"review_status={previous_review_status}->published"
            ),
        )
        await self._commit()
        await self._index_or_flag(profile.id)
        published_at = datetime.now(tz=UTC).isoformat()
        await publish_marketplace_event(
            self.event_producer,
            MarketplaceEventType.published,
            MarketplacePublishedPayload(
                agent_id=str(profile.id),
                published_at=published_at,
            ),
            self._correlation(workspace_id, profile.fqn),
        )
        if previous_scope != target_scope:
            await publish_marketplace_event(
                self.event_producer,
                MarketplaceEventType.scope_changed,
                MarketplaceScopeChangedPayload(
                    agent_id=str(profile.id),
                    from_scope=previous_scope,
                    to_scope=target_scope,
                    actor_user_id=str(actor_id),
                ),
                self._correlation(workspace_id, profile.fqn),
            )
        return await self._build_profile_response(profile)

    async def change_marketplace_scope(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        request: MarketplaceScopeChangeRequest,
        actor_id: UUID,
    ) -> AgentProfileResponse:
        """Change marketplace scope without publishing (UPD-049 FR /
        contracts/publish-and-review-rest.md)."""
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self._get_agent_or_raise(workspace_id, agent_id)
        target_scope = request.scope
        if target_scope == profile.marketplace_scope:
            return await self._build_profile_response(profile)
        if target_scope == "public_default_tenant":
            tenant = get_current_tenant()
            if tenant.kind != "default":
                raise PublicScopeNotAllowedForEnterpriseError(tenant.slug)
        previous_scope = profile.marketplace_scope
        profile.marketplace_scope = target_scope
        await self._commit()
        await self._index_or_flag(profile.id)
        await publish_marketplace_event(
            self.event_producer,
            MarketplaceEventType.scope_changed,
            MarketplaceScopeChangedPayload(
                agent_id=str(profile.id),
                from_scope=previous_scope,
                to_scope=target_scope,
                actor_user_id=str(actor_id),
            ),
            self._correlation(workspace_id, profile.fqn),
        )
        return await self._build_profile_response(profile)

    async def deprecate_listing(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        request: DeprecateListingRequest,
        actor_id: UUID,
    ) -> AgentProfileResponse:
        """Mark a published listing as deprecated (UPD-049). The listing
        disappears from public marketplace search; existing forks remain
        visible."""
        await self._assert_workspace_access(workspace_id, actor_id)
        profile = await self._get_agent_or_raise(workspace_id, agent_id)
        if not is_valid_review_transition(profile.review_status, "deprecated"):
            raise SubmissionAlreadyResolvedError(profile.id, profile.review_status)
        previous_review_status = profile.review_status
        profile.review_status = "deprecated"
        await self.repository.insert_lifecycle_audit(
            workspace_id=workspace_id,
            agent_profile_id=profile.id,
            previous_status=profile.status,
            new_status=profile.status,
            actor_id=actor_id,
            reason=(
                f"marketplace_deprecate: review_status="
                f"{previous_review_status}->deprecated; reason={request.reason!r}"
            ),
        )
        await self._commit()
        await self._index_or_flag(profile.id)
        await publish_marketplace_event(
            self.event_producer,
            MarketplaceEventType.deprecated,
            MarketplaceDeprecatedPayload(
                agent_id=str(profile.id),
                actor_user_id=str(actor_id),
                deprecation_reason=request.reason,
            ),
            self._correlation(workspace_id, profile.fqn),
        )
        return await self._build_profile_response(profile)

    async def fork_agent(
        self,
        source_id: UUID,
        request: ForkAgentRequest,
        actor_id: UUID,
    ) -> ForkAgentResponse:
        """UPD-049 — fork a visible agent into the consumer's tenant/workspace.

        Per research R7 and contracts/fork-rest.md:

        - Verifies source visibility via the regular RLS-filtered session;
          raises ``SourceAgentNotVisibleError`` (404) if not found.
        - Verifies the consumer's target workspace authorization.
        - Shallow-copies the source's operational fields (purpose, approach,
          role types, tags, mcp servers, data categories, default model
          binding); resets review fields; sets ``forked_from_agent_id``.
        - Surfaces tools the consumer's tenant doesn't have registered yet
          via the response's ``tool_dependencies_missing`` array.
        - Records audit-chain entry; publishes ``marketplace.forked``.
        """
        # Source visibility — RLS handles cross-tenant cuts. We use the
        # cross-workspace lookup helper because forks are intentionally
        # cross-workspace in the consumer's tenant (or cross-tenant via
        # the consume flag).
        source = await self._lookup_source_for_fork(source_id)
        if source is None:
            raise SourceAgentNotVisibleError(source_id)

        # Resolve target workspace.
        target_workspace_id = request.target_workspace_id
        if request.target_scope == "tenant":
            # For tenant scope we use the consumer's currently-active workspace
            # as the home; the agent will then be visible across all
            # workspaces in the tenant per the workspace-scope vs tenant-scope
            # distinction. The caller MUST have provided target_workspace_id
            # when target_scope == "workspace"; for tenant scope we fall back
            # to the request's target_workspace_id if provided, else require it.
            if target_workspace_id is None:
                # Pick the first workspace the actor can write to in this
                # tenant. This keeps the API ergonomic (consumer just says
                # "fork into my tenant" and the system picks a workspace).
                workspace_ids = await self.workspaces_service.get_user_workspace_ids(actor_id) \
                    if self.workspaces_service is not None else []
                if not workspace_ids:
                    raise WorkspaceAuthorizationError(uuid4())
                target_workspace_id = workspace_ids[0]
        assert target_workspace_id is not None
        await self._assert_workspace_access(target_workspace_id, actor_id)

        # UPD-049 refresh (102) T053 — fork quota integration. Verify the
        # consumer's tenant plan has agent-publish capacity before we
        # spend cycles building the fork. Closes 099 NOTES Backend
        # follow-up 1. Skipped silently if the quota_enforcer dependency
        # isn't wired (test contexts, local mode). Use getattr so tests
        # that bypass __init__ via __new__ don't AttributeError.
        quota_enforcer = getattr(self, "quota_enforcer", None)
        if quota_enforcer is not None and hasattr(
            quota_enforcer, "check_agent_publish"
        ):
            quota_result = await quota_enforcer.check_agent_publish(
                target_workspace_id
            )
            allowed = getattr(quota_result, "allowed", quota_result)
            if allowed is False:
                # Re-use the existing 402-quota_exceeded surface from the
                # publish path (the contract names the same error code).
                from platform.billing.exceptions import QuotaExceededError

                raise QuotaExceededError(
                    "agent_publish",
                    current=getattr(quota_result, "current", 0),
                    limit=getattr(quota_result, "limit", 0),
                )

        # Resolve target namespace — reuse the source's namespace name in the
        # consumer's tenant if it exists; otherwise fall back to a default
        # "forks" namespace.
        source_namespace_name = source.fqn.split(":", 1)[0] if ":" in source.fqn else "forks"
        namespace = await self.repository.get_namespace_by_name(
            target_workspace_id, source_namespace_name
        )
        if namespace is None:
            namespace = await self.repository.create_namespace(
                workspace_id=target_workspace_id,
                name=source_namespace_name,
                description=f"Forks of {source_namespace_name} agents",
                created_by=actor_id,
            )

        new_fqn = f"{namespace.name}:{request.new_name}"
        existing = await self.repository.get_agent_by_fqn(target_workspace_id, new_fqn)
        if existing is not None:
            raise NameTakenInTargetNamespaceError(new_fqn)

        # Shallow-copy operational fields onto the fork. Marketplace_scope is
        # consumer's choice (workspace or tenant — never public). Review
        # fields reset; forked_from_agent_id preserves provenance.
        fork = AgentProfile(
            workspace_id=target_workspace_id,
            namespace_id=namespace.id,
            local_name=request.new_name,
            fqn=new_fqn,
            display_name=source.display_name,
            purpose=source.purpose,
            approach=source.approach,
            role_types=list(source.role_types or []),
            custom_role_description=source.custom_role_description,
            visibility_agents=[],
            visibility_tools=[],
            tags=list(source.tags or []),
            mcp_server_refs=list(source.mcp_server_refs or []),
            data_categories=list(source.data_categories or []),
            status=LifecycleStatus.draft,
            maturity_level=0,
            embedding_status=EmbeddingStatus.pending,
            needs_reindex=True,
            created_by=actor_id,
            default_model_binding=source.default_model_binding,
            marketplace_scope=request.target_scope,
            review_status="draft",
            forked_from_agent_id=source.id,
        )
        self.repository.session.add(fork)
        await self.repository.session.flush()
        await self._commit()

        # UPD-049 refresh (102) T054 — tool-dependency cross-check.
        # Compare the source's mcp_server_refs against the MCP servers
        # registered in the consumer's tenant. Only servers NOT
        # registered for the consumer are flagged as missing. Closes
        # 099 NOTES Backend follow-up 2.
        tool_dependencies_missing = await self._tool_dependencies_missing_for(
            fork.mcp_server_refs or []
        )

        await publish_marketplace_event(
            self.event_producer,
            MarketplaceEventType.forked,
            MarketplaceForkedPayload(
                source_agent_id=str(source.id),
                fork_agent_id=str(fork.id),
                target_scope=request.target_scope,
                consumer_user_id=str(actor_id),
                consumer_tenant_id=str(get_current_tenant().id),
            ),
            self._correlation(target_workspace_id, fork.fqn),
        )
        marketplace_forks_total.labels(target_scope=request.target_scope).inc()
        LOGGER.info(
            "marketplace.forked",
            extra={
                "source_agent_id": str(source.id),
                "source_fqn": source.fqn,
                "fork_agent_id": str(fork.id),
                "fork_fqn": fork.fqn,
                "target_scope": request.target_scope,
                "actor_user_id": str(actor_id),
                "consumer_tenant_id": str(get_current_tenant().id),
                "tool_dependencies_missing_count": len(tool_dependencies_missing),
            },
        )
        return ForkAgentResponse(
            agent_id=fork.id,
            fqn=fork.fqn,
            marketplace_scope=fork.marketplace_scope,
            review_status=fork.review_status,
            forked_from_agent_id=source.id,
            forked_from_fqn=source.fqn,
            tool_dependencies_missing=tool_dependencies_missing,
        )

    async def _lookup_source_for_fork(self, source_id: UUID) -> AgentProfile | None:
        """Best-effort cross-workspace lookup for fork source.

        The repository's ``get_agent_by_id`` is workspace-scoped; for forks
        we need the row regardless of which workspace the consumer is
        currently in (RLS still filters by tenant + the public-visibility
        exceptions). This helper queries the same SELECT without the
        workspace clause via direct SQLAlchemy.
        """
        from sqlalchemy import select as sa_select
        result = await self.repository.session.execute(
            sa_select(AgentProfile).where(AgentProfile.id == source_id)
        )
        return result.scalar_one_or_none()

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
        if self.tagging_service is not None:
            await self.tagging_service.cascade_on_entity_deletion("agent", profile.id)
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

    async def list_visible_agents(self, requester: UUID | dict[str, Any]) -> set[UUID]:
        user_id = (
            UUID(str(requester.get("sub") or requester.get("user_id")))
            if isinstance(requester, dict)
            else UUID(str(requester))
        )
        if self.workspaces_service is None:
            return set()
        workspace_ids = set(await self.workspaces_service.get_user_workspace_ids(user_id))
        visible: set[UUID] = set()
        for workspace_id in workspace_ids:
            profiles, _total = await self.repository.list_agents_by_workspace(
                workspace_id,
                status=None,
                maturity_min=0,
                limit=10_000,
                offset=0,
                include_decommissioned=False,
            )
            visible.update(profile.id for profile in profiles)
        return visible

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
            data_categories=list(getattr(profile, "data_categories", []) or []),
            status=profile.status,
            maturity_level=int(profile.maturity_level),
            embedding_status=profile.embedding_status,
            workspace_id=profile.workspace_id,
            created_at=profile.created_at,
            current_revision=(
                self._revision_response(current_revision) if current_revision is not None else None
            ),
            default_model_binding=profile.default_model_binding,
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

    async def _check_pia_material_change(
        self,
        profile: AgentProfile,
        old_categories: list[str],
        new_categories: list[str],
    ) -> None:
        normalized_old = self._normalized_categories(old_categories)
        normalized_new = self._normalized_categories(new_categories)
        if set(normalized_old) == set(normalized_new):
            return
        if not set(normalized_new) & DATA_CATEGORIES_REQUIRING_PIA:
            return
        checker = getattr(self.pia_service, "check_material_change", None)
        if callable(checker):
            await checker("agent", profile.id, normalized_new)

    @staticmethod
    def _normalized_categories(categories: list[str] | tuple[str, ...] | None) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for category in categories or []:
            value = str(category).strip().casefold()
            if value and value not in seen:
                seen.add(value)
                normalized.append(value)
        return normalized

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

    async def _tool_dependencies_missing_for(
        self, mcp_server_refs: list[str]
    ) -> list[str]:
        """UPD-049 refresh (102) T054 — return the subset of
        ``mcp_server_refs`` that are NOT registered for any workspace
        inside the consumer's tenant.

        Refs are matched against both the registered server's
        ``endpoint_url`` and ``display_name`` so the publisher's choice
        of identifier shape does not bias the result. The current
        tenant context is taken from ``get_current_tenant()``.
        """
        if not mcp_server_refs:
            return []
        try:
            from sqlalchemy import text as _sql_text

            tenant = get_current_tenant()
            result = await self.repository.session.execute(
                _sql_text(
                    """
                    SELECT m.endpoint_url, m.display_name
                      FROM mcp_server_registrations m
                      JOIN workspaces_workspaces w ON w.id = m.workspace_id
                     WHERE w.tenant_id = :tenant_id
                       AND m.status = 'active'
                    """
                ),
                {"tenant_id": str(tenant.id)},
            )
            registered: set[str] = set()
            for row in result.mappings().all():
                if row["endpoint_url"]:
                    registered.add(str(row["endpoint_url"]))
                if row["display_name"]:
                    registered.add(str(row["display_name"]))
            return [ref for ref in mcp_server_refs if ref not in registered]
        except Exception:
            # Fall back to surfacing all refs as potentially-missing if
            # the lookup itself fails — preserves the safer signal for
            # the consumer (over-report missing rather than under-report).
            return list(mcp_server_refs)

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
