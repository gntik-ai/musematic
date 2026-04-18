from __future__ import annotations

import io
import re
import stat
import tarfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from platform.common.clients.qdrant import PointStruct
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.registry.models import (
    AgentMaturityRecord,
    AgentNamespace,
    AgentProfile,
    AgentRevision,
    AssessmentMethod,
    EmbeddingStatus,
    LifecycleAuditEntry,
    LifecycleStatus,
)
from platform.registry.schemas import (
    AgentDiscoveryParams,
    AgentListResponse,
    AgentManifest,
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
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from tests.auth_support import RecordingProducer


def build_registry_settings(**overrides: Any) -> PlatformSettings:
    return PlatformSettings(**overrides)


def _matches_visibility_patterns(fqn: str, patterns: list[str]) -> bool:
    if not patterns:
        return False
    for pattern in patterns:
        if "*" in pattern and re.fullmatch(r"[A-Za-z0-9:_*.-]+", pattern):
            regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
            if re.fullmatch(regex, fqn):
                return True
            continue
        if re.fullmatch(pattern, fqn):
            return True
    return False


def build_manifest_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "local_name": "kyc-verifier",
        "version": "1.0.0",
        "purpose": "Verifies customer identity documents for compliance workflows.",
        "role_types": ["executor"],
        "approach": "Reads the manifest, checks evidence, and emits a verdict.",
        "maturity_level": 1,
        "reasoning_modes": ["deterministic"],
        "tags": ["kyc", "finance"],
        "display_name": "KYC Verifier",
    }
    payload.update(overrides)
    return payload


def build_manifest(**overrides: Any) -> AgentManifest:
    return AgentManifest.model_validate(build_manifest_payload(**overrides))


def build_tar_package(
    *,
    manifest_payload: dict[str, Any] | None = None,
    manifest_name: str = "manifest.yaml",
    extra_files: dict[str, bytes] | None = None,
    symlink_target: str | None = None,
) -> bytes:
    buffer = io.BytesIO()
    payload = manifest_payload or build_manifest_payload()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        manifest_bytes = (
            _yaml_bytes(payload) if manifest_name.endswith(".yaml") else _json_bytes(payload)
        )
        manifest_info = tarfile.TarInfo(name=manifest_name)
        manifest_info.size = len(manifest_bytes)
        archive.addfile(manifest_info, io.BytesIO(manifest_bytes))
        for name, content in sorted((extra_files or {}).items()):
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        if symlink_target is not None:
            symlink = tarfile.TarInfo(name="link")
            symlink.type = tarfile.SYMTYPE
            symlink.linkname = symlink_target
            archive.addfile(symlink)
    return buffer.getvalue()


def build_zip_package(
    *,
    manifest_payload: dict[str, Any] | None = None,
    manifest_name: str = "manifest.yaml",
    extra_files: dict[str, bytes] | None = None,
    symlink_target: str | None = None,
) -> bytes:
    buffer = io.BytesIO()
    payload = manifest_payload or build_manifest_payload()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        manifest_bytes = (
            _yaml_bytes(payload) if manifest_name.endswith(".yaml") else _json_bytes(payload)
        )
        archive.writestr(manifest_name, manifest_bytes)
        for name, content in sorted((extra_files or {}).items()):
            archive.writestr(name, content)
        if symlink_target is not None:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, symlink_target.encode("utf-8"))
    return buffer.getvalue()


def build_namespace(
    *,
    namespace_id: UUID | None = None,
    workspace_id: UUID | None = None,
    created_by: UUID | None = None,
    name: str = "finance-ops",
    description: str | None = "Financial operations agents",
) -> AgentNamespace:
    now = datetime.now(UTC)
    namespace = AgentNamespace(
        id=namespace_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        name=name,
        description=description,
        created_by=created_by or uuid4(),
    )
    namespace.created_at = now
    namespace.updated_at = now
    return namespace


def build_profile(
    *,
    profile_id: UUID | None = None,
    workspace_id: UUID | None = None,
    namespace: AgentNamespace | None = None,
    local_name: str = "kyc-verifier",
    display_name: str | None = "KYC Verifier",
    purpose: str = "Verifies customer identity documents for compliance workflows.",
    approach: str | None = "Extract evidence and compare against policy.",
    role_types: list[str] | None = None,
    custom_role_description: str | None = None,
    visibility_agents: list[str] | None = None,
    visibility_tools: list[str] | None = None,
    tags: list[str] | None = None,
    status: LifecycleStatus = LifecycleStatus.draft,
    maturity_level: int = 1,
    embedding_status: EmbeddingStatus = EmbeddingStatus.pending,
    needs_reindex: bool = False,
    created_by: UUID | None = None,
) -> AgentProfile:
    now = datetime.now(UTC)
    resolved_namespace = namespace or build_namespace(workspace_id=workspace_id)
    resolved_workspace_id = workspace_id or resolved_namespace.workspace_id
    profile = AgentProfile(
        id=profile_id or uuid4(),
        workspace_id=resolved_workspace_id,
        namespace_id=resolved_namespace.id,
        local_name=local_name,
        fqn=f"{resolved_namespace.name}:{local_name}",
        display_name=display_name,
        purpose=purpose,
        approach=approach,
        role_types=role_types or ["executor"],
        custom_role_description=custom_role_description,
        visibility_agents=visibility_agents or [],
        visibility_tools=visibility_tools or [],
        tags=tags or ["kyc", "finance"],
        status=status,
        maturity_level=maturity_level,
        embedding_status=embedding_status,
        needs_reindex=needs_reindex,
        created_by=created_by or uuid4(),
    )
    profile.namespace = resolved_namespace
    profile.created_at = now
    profile.updated_at = now
    profile.deleted_at = None
    return profile


def build_revision(
    *,
    revision_id: UUID | None = None,
    agent_profile: AgentProfile | None = None,
    workspace_id: UUID | None = None,
    version: str = "1.0.0",
    storage_key: str | None = None,
    manifest_snapshot: dict[str, Any] | None = None,
    uploaded_by: UUID | None = None,
) -> AgentRevision:
    now = datetime.now(UTC)
    profile = agent_profile or build_profile(workspace_id=workspace_id)
    revision = AgentRevision(
        id=revision_id or uuid4(),
        workspace_id=workspace_id or profile.workspace_id,
        agent_profile_id=profile.id,
        version=version,
        sha256_digest="a" * 64,
        storage_key=storage_key or f"{profile.workspace_id}/{profile.fqn}/{version}.tar.gz",
        manifest_snapshot=manifest_snapshot
        or build_manifest_payload(local_name=profile.local_name),
        uploaded_by=uploaded_by or uuid4(),
    )
    revision.created_at = now
    revision.updated_at = now
    revision.agent_profile = profile
    return revision


def build_lifecycle_audit(
    *,
    entry_id: UUID | None = None,
    agent_profile_id: UUID | None = None,
    workspace_id: UUID | None = None,
    previous_status: LifecycleStatus = LifecycleStatus.draft,
    new_status: LifecycleStatus = LifecycleStatus.validated,
    actor_id: UUID | None = None,
    reason: str | None = None,
) -> LifecycleAuditEntry:
    now = datetime.now(UTC)
    entry = LifecycleAuditEntry(
        id=entry_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        agent_profile_id=agent_profile_id or uuid4(),
        previous_status=previous_status,
        new_status=new_status,
        actor_id=actor_id or uuid4(),
        reason=reason,
    )
    entry.created_at = now
    entry.updated_at = now
    return entry


def build_maturity_record(
    *,
    record_id: UUID | None = None,
    workspace_id: UUID | None = None,
    agent_profile_id: UUID | None = None,
    previous_level: int = 0,
    new_level: int = 1,
    actor_id: UUID | None = None,
    reason: str | None = None,
) -> AgentMaturityRecord:
    now = datetime.now(UTC)
    record = AgentMaturityRecord(
        id=record_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        agent_profile_id=agent_profile_id or uuid4(),
        previous_level=previous_level,
        new_level=new_level,
        assessment_method=AssessmentMethod.system_assessed,
        reason=reason,
        actor_id=actor_id or uuid4(),
    )
    record.created_at = now
    record.updated_at = now
    return record


def build_namespace_response(namespace: AgentNamespace) -> NamespaceResponse:
    return NamespaceResponse(
        id=namespace.id,
        name=namespace.name,
        description=namespace.description,
        workspace_id=namespace.workspace_id,
        created_at=namespace.created_at,
        created_by=namespace.created_by,
    )


def build_revision_response(revision: AgentRevision) -> AgentRevisionResponse:
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


def build_profile_response(
    profile: AgentProfile,
    revision: AgentRevision | None = None,
) -> AgentProfileResponse:
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
        status=profile.status,
        maturity_level=profile.maturity_level,
        embedding_status=profile.embedding_status,
        workspace_id=profile.workspace_id,
        created_at=profile.created_at,
        current_revision=None if revision is None else build_revision_response(revision),
    )


def build_list_response(*profiles: AgentProfile) -> AgentListResponse:
    items = [build_profile_response(profile) for profile in profiles]
    return AgentListResponse(items=items, total=len(items), limit=20, offset=0)


def build_lifecycle_audit_response(entry: LifecycleAuditEntry) -> LifecycleAuditResponse:
    return LifecycleAuditResponse(
        id=entry.id,
        agent_profile_id=entry.agent_profile_id,
        previous_status=entry.previous_status,
        new_status=entry.new_status,
        actor_id=entry.actor_id,
        reason=entry.reason,
        created_at=entry.created_at,
    )


@dataclass
class ExecuteResultStub:
    one: Any = None
    many: list[Any] = field(default_factory=list)

    def scalar_one_or_none(self) -> Any:
        return self.one

    def scalars(self) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: list(self.many))


@dataclass
class SessionStub:
    execute_results: list[ExecuteResultStub] = field(default_factory=list)
    scalar_results: list[Any] = field(default_factory=list)
    get_results: dict[tuple[type[Any], UUID], Any] = field(default_factory=dict)
    added: list[Any] = field(default_factory=list)
    deleted: list[Any] = field(default_factory=list)
    executed: list[Any] = field(default_factory=list)
    scalar_calls: list[Any] = field(default_factory=list)
    commit_calls: int = 0
    rollback_calls: int = 0
    flush_calls: int = 0

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def delete(self, item: Any) -> None:
        self.deleted.append(item)

    async def flush(self) -> None:
        self.flush_calls += 1

    async def execute(self, statement: Any) -> ExecuteResultStub:
        self.executed.append(statement)
        return self.execute_results.pop(0) if self.execute_results else ExecuteResultStub()

    async def scalar(self, statement: Any) -> Any:
        self.scalar_calls.append(statement)
        return self.scalar_results.pop(0) if self.scalar_results else None

    async def get(self, model: type[Any], identifier: UUID) -> Any:
        return self.get_results.get((model, identifier))

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


@dataclass
class ObjectStorageStub:
    buckets: set[str] = field(default_factory=set)
    objects: dict[tuple[str, str], bytes] = field(default_factory=dict)
    uploaded: list[tuple[str, str, bytes, str]] = field(default_factory=list)
    deleted: list[tuple[str, str]] = field(default_factory=list)
    fail_upload: Exception | None = None

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        self.buckets.add(bucket)

    async def upload_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        del metadata
        if self.fail_upload is not None:
            raise self.fail_upload
        self.uploaded.append((bucket, key, data, content_type))
        self.objects[(bucket, key)] = data

    async def download_object(self, bucket: str, key: str, version_id: str | None = None) -> bytes:
        del version_id
        return self.objects[(bucket, key)]

    async def delete_object(self, bucket: str, key: str, version_id: str | None = None) -> None:
        del version_id
        self.deleted.append((bucket, key))
        self.objects.pop((bucket, key), None)

    async def object_exists(self, bucket: str, key: str) -> bool:
        return (bucket, key) in self.objects

    async def list_objects(self, bucket: str, prefix: str = "") -> list[str]:
        return [
            key
            for current_bucket, key in self.objects
            if current_bucket == bucket and key.startswith(prefix)
        ]


@dataclass
class RawOpenSearchSearchStub:
    search_response: dict[str, Any] = field(default_factory=dict)
    search_calls: list[dict[str, Any]] = field(default_factory=list)

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        self.search_calls.append(kwargs)
        return self.search_response


@dataclass
class AsyncOpenSearchStub:
    raw_client: Any = field(default_factory=RawOpenSearchSearchStub)
    indexed: list[tuple[str, dict[str, Any], str | None, bool]] = field(default_factory=list)
    fail_index: Exception | None = None
    connected: bool = False
    closed: bool = False

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True

    async def health_check(self) -> bool:
        return True

    async def _ensure_client(self) -> Any:
        return self.raw_client

    async def index_document(
        self,
        index: str,
        document: dict[str, Any],
        document_id: str | None = None,
        refresh: bool = False,
    ) -> str:
        if self.fail_index is not None:
            raise self.fail_index
        self.indexed.append((index, document, document_id, refresh))
        return document_id or str(uuid4())


@dataclass
class AsyncQdrantStub:
    upserts: list[tuple[str, list[PointStruct]]] = field(default_factory=list)
    create_calls: list[dict[str, Any]] = field(default_factory=list)
    connected: bool = False
    closed: bool = False

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True

    async def health_check(self) -> bool:
        return True

    async def upsert_vectors(self, collection: str, points: list[PointStruct]) -> None:
        self.upserts.append((collection, points))

    async def create_collection_if_not_exists(self, **kwargs: Any) -> bool:
        self.create_calls.append(kwargs)
        return True


@dataclass
class WorkspacesServiceStub:
    workspace_ids_by_user: dict[UUID, list[UUID]] = field(default_factory=dict)
    visibility_by_workspace: dict[UUID, SimpleNamespace | None] = field(default_factory=dict)
    getter_mode: str = "workspace"

    async def get_user_workspace_ids(self, user_id: UUID) -> list[UUID]:
        return list(self.workspace_ids_by_user.get(user_id, []))

    async def get_workspace_visibility_grant(self, workspace_id: UUID) -> SimpleNamespace | None:
        if self.getter_mode != "workspace":
            raise AttributeError
        return self.visibility_by_workspace.get(workspace_id)

    async def get_visibility_grant(self, workspace_id: UUID) -> SimpleNamespace | None:
        if self.getter_mode != "legacy":
            raise AttributeError
        return self.visibility_by_workspace.get(workspace_id)


class RegistryRepoStub:
    def __init__(self) -> None:
        self.session = SessionStub()
        self.namespaces_by_id: dict[UUID, AgentNamespace] = {}
        self.namespaces_by_name: dict[tuple[UUID, str], AgentNamespace] = {}
        self.profiles_by_id: dict[UUID, AgentProfile] = {}
        self.profiles_by_fqn: dict[tuple[UUID, str], AgentProfile] = {}
        self.revisions_by_profile: dict[UUID, list[AgentRevision]] = {}
        self.lifecycle_by_profile: dict[UUID, list[LifecycleAuditEntry]] = {}
        self.maturity_records: list[AgentMaturityRecord] = []
        self.keyword_ids: list[UUID] = []
        self.keyword_total: int = 0
        self.reindex_profiles: list[AgentProfile] = []

    async def create_namespace(
        self,
        *,
        workspace_id: UUID,
        name: str,
        description: str | None,
        created_by: UUID,
    ) -> AgentNamespace:
        namespace = build_namespace(
            workspace_id=workspace_id,
            created_by=created_by,
            name=name,
            description=description,
        )
        self.namespaces_by_id[namespace.id] = namespace
        self.namespaces_by_name[(workspace_id, name)] = namespace
        return namespace

    async def get_namespace_by_name(self, workspace_id: UUID, name: str) -> AgentNamespace | None:
        return self.namespaces_by_name.get((workspace_id, name))

    async def get_namespace_by_id(
        self,
        workspace_id: UUID,
        namespace_id: UUID,
    ) -> AgentNamespace | None:
        namespace = self.namespaces_by_id.get(namespace_id)
        if namespace is None or namespace.workspace_id != workspace_id:
            return None
        return namespace

    async def list_namespaces(self, workspace_id: UUID) -> list[AgentNamespace]:
        return [
            namespace
            for namespace in self.namespaces_by_id.values()
            if namespace.workspace_id == workspace_id
        ]

    async def delete_namespace(self, namespace: AgentNamespace) -> None:
        self.namespaces_by_id.pop(namespace.id, None)
        self.namespaces_by_name.pop((namespace.workspace_id, namespace.name), None)

    async def namespace_has_agents(self, namespace_id: UUID) -> bool:
        return any(profile.namespace_id == namespace_id for profile in self.profiles_by_id.values())

    async def upsert_agent_profile(
        self,
        *,
        workspace_id: UUID,
        namespace: AgentNamespace,
        local_name: str,
        display_name: str | None,
        purpose: str,
        approach: str | None,
        role_types: list[str],
        custom_role_description: str | None,
        tags: list[str],
        maturity_level: int,
        actor_id: UUID,
    ) -> tuple[AgentProfile, bool]:
        key = (workspace_id, f"{namespace.name}:{local_name}")
        existing = self.profiles_by_fqn.get(key)
        if existing is not None and existing.status is not LifecycleStatus.decommissioned:
            existing.display_name = display_name
            existing.purpose = purpose
            existing.approach = approach
            existing.role_types = role_types
            existing.custom_role_description = custom_role_description
            existing.tags = tags
            existing.maturity_level = maturity_level
            existing.embedding_status = EmbeddingStatus.pending
            return existing, False

        profile = build_profile(
            workspace_id=workspace_id,
            namespace=namespace,
            local_name=local_name,
            display_name=display_name,
            purpose=purpose,
            approach=approach,
            role_types=role_types,
            custom_role_description=custom_role_description,
            tags=tags,
            maturity_level=maturity_level,
            created_by=actor_id,
        )
        self.profiles_by_id[profile.id] = profile
        self.profiles_by_fqn[key] = profile
        return profile, True

    async def update_agent_profile(self, profile: AgentProfile, **fields: Any) -> AgentProfile:
        from platform.registry.exceptions import DecommissionImmutableError

        immutable_fields = [
            key
            for key in ("decommissioned_at", "decommission_reason", "decommissioned_by")
            if key in fields and getattr(profile, key) is not None and fields[key] != getattr(profile, key)
        ]
        if immutable_fields:
            raise DecommissionImmutableError(immutable_fields)
        for key, value in fields.items():
            setattr(profile, key, value)
        profile.updated_at = datetime.now(UTC)
        return profile

    async def get_agent_by_id(self, workspace_id: UUID, agent_id: UUID) -> AgentProfile | None:
        profile = self.profiles_by_id.get(agent_id)
        if profile is None or profile.workspace_id != workspace_id:
            return None
        return profile

    async def get_agent_by_id_any(self, agent_id: UUID) -> AgentProfile | None:
        return self.profiles_by_id.get(agent_id)

    async def get_agent_by_fqn(
        self,
        workspace_id: UUID,
        fqn: str,
        *,
        include_decommissioned: bool = False,
    ) -> AgentProfile | None:
        profile = self.profiles_by_fqn.get((workspace_id, fqn))
        if profile is None:
            return None
        if not include_decommissioned and profile.status is LifecycleStatus.decommissioned:
            return None
        return profile

    async def get_by_fqn(self, workspace_id: UUID, fqn: str) -> AgentProfile | None:
        return await self.get_agent_by_fqn(
            workspace_id,
            fqn,
            include_decommissioned=True,
        )

    async def list_agents_by_workspace(
        self,
        workspace_id: UUID,
        *,
        status: LifecycleStatus | None,
        maturity_min: int,
        limit: int,
        offset: int,
        visibility_filter: Any | None = None,
        include_decommissioned: bool = False,
    ) -> tuple[list[AgentProfile], int]:
        profiles = [
            profile
            for profile in self.profiles_by_id.values()
            if profile.workspace_id == workspace_id
            and profile.maturity_level >= maturity_min
            and (status is None or profile.status == status)
            and (include_decommissioned or profile.status is not LifecycleStatus.decommissioned)
            and (
                visibility_filter is None
                or _matches_visibility_patterns(
                    profile.fqn,
                    list(getattr(visibility_filter, "agent_patterns", []) or []),
                )
            )
        ]
        profiles.sort(key=lambda profile: (profile.created_at, profile.id))
        return profiles[offset : offset + limit], len(profiles)

    async def get_agents_by_ids(
        self,
        workspace_id: UUID,
        agent_ids: list[UUID],
        *,
        visibility_filter: Any | None = None,
    ) -> list[AgentProfile]:
        return [
            profile
            for agent_id in agent_ids
            if (profile := await self.get_agent_by_id(workspace_id, agent_id)) is not None
            and (
                visibility_filter is None
                or _matches_visibility_patterns(
                    profile.fqn,
                    list(getattr(visibility_filter, "agent_patterns", []) or []),
                )
            )
        ]

    async def insert_revision(
        self,
        *,
        revision_id: UUID,
        workspace_id: UUID,
        agent_profile_id: UUID,
        version: str,
        sha256_digest: str,
        storage_key: str,
        manifest_snapshot: dict[str, Any],
        uploaded_by: UUID,
    ) -> AgentRevision:
        revision = build_revision(
            revision_id=revision_id,
            agent_profile=self.profiles_by_id[agent_profile_id],
            workspace_id=workspace_id,
            version=version,
            storage_key=storage_key,
            manifest_snapshot=manifest_snapshot,
            uploaded_by=uploaded_by,
        )
        revision.sha256_digest = sha256_digest
        self.revisions_by_profile.setdefault(agent_profile_id, []).append(revision)
        return revision

    async def get_revision_by_id(self, revision_id: UUID) -> AgentRevision | None:
        for revisions in self.revisions_by_profile.values():
            for revision in revisions:
                if revision.id == revision_id:
                    return revision
        return None

    async def get_latest_revision(self, agent_profile_id: UUID) -> AgentRevision | None:
        revisions = self.revisions_by_profile.get(agent_profile_id, [])
        return revisions[-1] if revisions else None

    async def list_revisions(self, agent_profile_id: UUID) -> list[AgentRevision]:
        return list(self.revisions_by_profile.get(agent_profile_id, []))

    async def persist_decommission(
        self,
        profile: AgentProfile,
        *,
        reason: str,
        actor_id: UUID,
    ) -> AgentProfile:
        if profile.status is LifecycleStatus.decommissioned:
            return profile
        profile.status = LifecycleStatus.decommissioned
        profile.decommissioned_at = datetime.now(UTC)
        profile.decommission_reason = reason
        profile.decommissioned_by = actor_id
        profile.updated_at = datetime.now(UTC)
        return profile

    async def insert_maturity_record(
        self,
        *,
        workspace_id: UUID,
        agent_profile_id: UUID,
        previous_level: int,
        new_level: int,
        assessment_method: AssessmentMethod,
        reason: str | None,
        actor_id: UUID,
    ) -> AgentMaturityRecord:
        record = build_maturity_record(
            workspace_id=workspace_id,
            agent_profile_id=agent_profile_id,
            previous_level=previous_level,
            new_level=new_level,
            actor_id=actor_id,
            reason=reason,
        )
        record.assessment_method = assessment_method
        self.maturity_records.append(record)
        return record

    async def insert_lifecycle_audit(
        self,
        *,
        workspace_id: UUID,
        agent_profile_id: UUID,
        previous_status: LifecycleStatus,
        new_status: LifecycleStatus,
        actor_id: UUID,
        reason: str | None,
    ) -> LifecycleAuditEntry:
        entry = build_lifecycle_audit(
            workspace_id=workspace_id,
            agent_profile_id=agent_profile_id,
            previous_status=previous_status,
            new_status=new_status,
            actor_id=actor_id,
            reason=reason,
        )
        self.lifecycle_by_profile.setdefault(agent_profile_id, []).append(entry)
        return entry

    async def list_lifecycle_audit(self, agent_profile_id: UUID) -> list[LifecycleAuditEntry]:
        return list(self.lifecycle_by_profile.get(agent_profile_id, []))

    async def get_agents_needing_reindex(self, limit: int = 100) -> list[AgentProfile]:
        return list(self.reindex_profiles[:limit])

    async def set_needs_reindex(self, agent_profile_id: UUID, needs_reindex: bool) -> None:
        profile = self.profiles_by_id.get(agent_profile_id)
        if profile is not None:
            profile.needs_reindex = needs_reindex

    async def set_embedding_status(
        self,
        agent_profile_id: UUID,
        status: EmbeddingStatus,
    ) -> None:
        profile = self.profiles_by_id.get(agent_profile_id)
        if profile is not None:
            profile.embedding_status = status

    async def search_by_keyword(
        self,
        *,
        workspace_id: UUID,
        keyword: str,
        status: LifecycleStatus | None,
        maturity_min: int,
        limit: int,
        offset: int,
        index_name: str,
    ) -> tuple[list[UUID], int]:
        del workspace_id, keyword, status, maturity_min, limit, offset, index_name
        return list(self.keyword_ids), self.keyword_total


class RouterRegistryServiceStub:
    def __init__(self) -> None:
        namespace = build_namespace()
        profile = build_profile(namespace=namespace)
        revision = build_revision(agent_profile=profile)
        audit = build_lifecycle_audit(
            agent_profile_id=profile.id,
            workspace_id=profile.workspace_id,
        )

        self.namespace = namespace
        self.profile = profile
        self.revision = revision
        self.audit = audit
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    async def create_namespace(
        self,
        workspace_id: UUID,
        payload: NamespaceCreate,
        actor_id: UUID,
    ) -> NamespaceResponse:
        self._record("create_namespace", workspace_id, payload, actor_id)
        return build_namespace_response(self.namespace)

    async def list_namespaces(self, workspace_id: UUID, actor_id: UUID) -> NamespaceListResponse:
        self._record("list_namespaces", workspace_id, actor_id)
        return NamespaceListResponse(items=[build_namespace_response(self.namespace)], total=1)

    async def delete_namespace(
        self,
        workspace_id: UUID,
        namespace_id: UUID,
        actor_id: UUID,
    ) -> None:
        self._record("delete_namespace", workspace_id, namespace_id, actor_id)

    async def upload_agent(
        self,
        *,
        workspace_id: UUID,
        namespace_name: str,
        package_bytes: bytes,
        filename: str,
        actor_id: UUID,
    ) -> AgentUploadResponse:
        self._record(
            "upload_agent",
            workspace_id,
            namespace_name,
            package_bytes,
            filename,
            actor_id,
        )
        return AgentUploadResponse(
            agent_profile=build_profile_response(self.profile, self.revision),
            revision=build_revision_response(self.revision),
            created=True,
        )

    async def resolve_fqn(
        self,
        fqn: str,
        *,
        workspace_id: UUID,
        actor_id: UUID | None = None,
        requesting_agent_id: UUID | None = None,
    ) -> AgentProfileResponse:
        self._record("resolve_fqn", fqn, workspace_id, actor_id, requesting_agent_id)
        return build_profile_response(self.profile, self.revision)

    async def list_agents(
        self,
        params: AgentDiscoveryParams,
        *,
        requesting_agent_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> AgentListResponse:
        self._record("list_agents", params, requesting_agent_id, actor_id)
        return build_list_response(self.profile)

    async def get_agent(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        *,
        actor_id: UUID | None = None,
        requesting_agent_id: UUID | None = None,
    ) -> AgentProfileResponse:
        self._record("get_agent", workspace_id, agent_id, actor_id, requesting_agent_id)
        return build_profile_response(self.profile, self.revision)

    async def patch_agent(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        payload: AgentPatch,
        actor_id: UUID,
    ) -> AgentProfileResponse:
        self._record("patch_agent", workspace_id, agent_id, payload, actor_id)
        return build_profile_response(self.profile, self.revision)

    async def transition_lifecycle(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        payload: LifecycleTransitionRequest,
        actor_id: UUID,
    ) -> AgentProfileResponse:
        self._record("transition_lifecycle", workspace_id, agent_id, payload, actor_id)
        return build_profile_response(self.profile, self.revision)

    async def decommission_agent(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        reason: str,
        actor_id: UUID,
        runtime_controller: Any | None,
        *,
        actor_is_platform_admin: bool = False,
    ):
        del runtime_controller
        self._record(
            "decommission_agent",
            workspace_id,
            agent_id,
            reason,
            actor_id,
            actor_is_platform_admin,
        )
        from platform.registry.schemas import AgentDecommissionResponse

        return AgentDecommissionResponse(
            agent_id=self.profile.id,
            agent_fqn=self.profile.fqn,
            decommissioned_at=self.profile.updated_at,
            decommission_reason=reason,
            decommissioned_by=actor_id,
            active_instances_stopped=0,
        )

    async def update_maturity(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        payload: MaturityUpdateRequest,
        actor_id: UUID,
    ) -> AgentProfileResponse:
        self._record("update_maturity", workspace_id, agent_id, payload, actor_id)
        return build_profile_response(self.profile, self.revision)

    async def list_revisions(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        actor_id: UUID,
    ) -> list[AgentRevisionResponse]:
        self._record("list_revisions", workspace_id, agent_id, actor_id)
        return [build_revision_response(self.revision)]

    async def list_lifecycle_audit(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        actor_id: UUID,
    ) -> LifecycleAuditListResponse:
        self._record("list_lifecycle_audit", workspace_id, agent_id, actor_id)
        return LifecycleAuditListResponse(
            items=[build_lifecycle_audit_response(self.audit)],
            total=1,
        )


def build_recording_producer() -> RecordingProducer:
    return RecordingProducer()


def build_correlation(
    workspace_id: UUID | None = None,
    *,
    agent_fqn: str | None = None,
) -> CorrelationContext:
    return CorrelationContext(
        correlation_id=uuid4(),
        workspace_id=workspace_id,
        agent_fqn=agent_fqn,
    )


def _yaml_bytes(payload: dict[str, Any]) -> bytes:
    lines: list[str] = []
    for key, value in payload.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _json_bytes(payload: dict[str, Any]) -> bytes:
    import json

    return json.dumps(payload).encode("utf-8")
