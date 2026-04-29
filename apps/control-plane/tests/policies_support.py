from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.policies.dependencies import get_policy_service
from platform.policies.models import (
    AttachmentTargetType,
    EnforcementComponent,
    PolicyAttachment,
    PolicyBlockedActionRecord,
    PolicyBundleCache,
    PolicyPolicy,
    PolicyScopeType,
    PolicyStatus,
    PolicyVersion,
)
from platform.policies.router import router as policies_router
from platform.policies.schemas import (
    BudgetLimitsSchema,
    EnforcementBundle,
    EnforcementRuleSchema,
    MaturityGateRuleSchema,
    PolicyCreate,
    PolicyRulesSchema,
    PurposeScopeSchema,
    SafetyRuleSchema,
)
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI

from tests.auth_support import FakeAsyncRedisClient, MemoryRedis
from tests.registry_support import ExecuteResultStub


def stamp(model: Any, *, created_at: datetime | None = None) -> Any:
    now = created_at or datetime.now(UTC)
    if getattr(model, "id", None) is None:
        model.id = uuid4()
    if getattr(model, "created_at", None) is None:
        model.created_at = now
    if getattr(model, "updated_at", None) is None:
        model.updated_at = now
    return model


def build_rules(
    *,
    enforcement_rules: list[EnforcementRuleSchema] | None = None,
    maturity_gate_rules: list[MaturityGateRuleSchema] | None = None,
    purpose_scopes: list[PurposeScopeSchema] | None = None,
    budget_limits: BudgetLimitsSchema | None = None,
    safety_rules: list[SafetyRuleSchema] | None = None,
    allowed_namespaces: list[str] | None = None,
    allowed_classifications: list[str] | None = None,
    allowed_agent_fqns: list[str] | None = None,
) -> PolicyRulesSchema:
    return PolicyRulesSchema(
        enforcement_rules=enforcement_rules or [],
        maturity_gate_rules=maturity_gate_rules or [],
        purpose_scopes=purpose_scopes or [],
        budget_limits=budget_limits or BudgetLimitsSchema(),
        safety_rules=safety_rules or [],
        allowed_namespaces=allowed_namespaces or [],
        allowed_classifications=allowed_classifications or [],
        allowed_agent_fqns=allowed_agent_fqns or [],
    )


def build_policy_create(
    *,
    name: str = "Finance Policy",
    description: str | None = "Policy description",
    scope_type: PolicyScopeType = PolicyScopeType.workspace,
    workspace_id: UUID | None = None,
    rules: PolicyRulesSchema | None = None,
    change_summary: str | None = "Initial version",
) -> PolicyCreate:
    return PolicyCreate(
        name=name,
        description=description,
        scope_type=scope_type,
        workspace_id=workspace_id,
        rules=rules or build_rules(),
        change_summary=change_summary,
    )


def build_policy(
    *,
    policy_id: UUID | None = None,
    name: str = "Finance Policy",
    description: str | None = "Policy description",
    scope_type: PolicyScopeType = PolicyScopeType.workspace,
    status: PolicyStatus = PolicyStatus.active,
    workspace_id: UUID | None = None,
    created_by: UUID | None = None,
    updated_by: UUID | None = None,
    current_version: PolicyVersion | None = None,
) -> PolicyPolicy:
    policy = PolicyPolicy(
        id=policy_id or uuid4(),
        name=name,
        description=description,
        scope_type=scope_type,
        status=status,
        workspace_id=workspace_id,
        created_by=created_by,
        updated_by=updated_by,
        current_version_id=current_version.id if current_version is not None else None,
    )
    stamp(policy)
    policy.versions = []
    policy.attachments = []
    if current_version is not None:
        policy.current_version = current_version
        policy.versions = [current_version]
    return policy


def build_version(
    *,
    version_id: UUID | None = None,
    policy_id: UUID | None = None,
    version_number: int = 1,
    rules: PolicyRulesSchema | dict[str, Any] | None = None,
    change_summary: str | None = "Initial version",
    created_by: UUID | None = None,
) -> PolicyVersion:
    payload = (
        rules.model_dump(mode="json")
        if isinstance(rules, PolicyRulesSchema)
        else rules
        if rules is not None
        else build_rules().model_dump(mode="json")
    )
    version = PolicyVersion(
        id=version_id or uuid4(),
        policy_id=policy_id or uuid4(),
        version_number=version_number,
        rules=payload,
        change_summary=change_summary,
        created_by=created_by,
    )
    stamp(version)
    return version


def build_attachment(
    *,
    attachment_id: UUID | None = None,
    policy: PolicyPolicy,
    version: PolicyVersion,
    target_type: AttachmentTargetType,
    target_id: str | None,
    created_by: UUID | None = None,
    is_active: bool = True,
) -> PolicyAttachment:
    attachment = PolicyAttachment(
        id=attachment_id or uuid4(),
        policy_id=policy.id,
        policy_version_id=version.id,
        target_type=target_type,
        target_id=target_id,
        is_active=is_active,
        created_by=created_by,
    )
    stamp(attachment)
    attachment.policy = policy
    attachment.policy_version = version
    return attachment


def build_blocked_record(
    *,
    record_id: UUID | None = None,
    agent_id: UUID | None = None,
    agent_fqn: str = "finance:agent",
    enforcement_component: EnforcementComponent = EnforcementComponent.tool_gateway,
    action_type: str = "tool_invocation",
    target: str = "calculator",
    block_reason: str = "permission_denied",
    execution_id: UUID | None = None,
    workspace_id: UUID | None = None,
    policy_rule_ref: dict[str, Any] | None = None,
) -> PolicyBlockedActionRecord:
    record = PolicyBlockedActionRecord(
        id=record_id or uuid4(),
        agent_id=agent_id or uuid4(),
        agent_fqn=agent_fqn,
        enforcement_component=enforcement_component,
        action_type=action_type,
        target=target,
        block_reason=block_reason,
        execution_id=execution_id,
        workspace_id=workspace_id,
        policy_rule_ref=policy_rule_ref,
    )
    stamp(record)
    return record


def attach_version_scope(
    version: PolicyVersion,
    *,
    level: int,
    scope_type: PolicyScopeType,
    scope_target_id: str | None = None,
) -> PolicyVersion:
    version_any = version
    version_any._scope_level = level
    version_any._scope_type = scope_type
    version_any._scope_target_id = scope_target_id
    return version


@dataclass
class RecorderSession:
    flush_calls: int = 0
    commit_calls: int = 0

    async def flush(self) -> None:
        self.flush_calls += 1

    async def commit(self) -> None:
        self.commit_calls += 1


@dataclass
class WorkspaceRepoStub:
    workspace_ids: set[UUID] = field(default_factory=set)

    async def get_workspace_by_id_any(self, workspace_id: UUID) -> UUID | None:
        return workspace_id if workspace_id in self.workspace_ids else None


@dataclass
class WorkspacesPolicyStub:
    workspace_ids: set[UUID] = field(default_factory=set)
    visibility_by_workspace: dict[UUID, SimpleNamespace | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.repo = WorkspaceRepoStub(self.workspace_ids)

    async def get_workspace_visibility_grant(self, workspace_id: UUID) -> SimpleNamespace | None:
        return self.visibility_by_workspace.get(workspace_id)


@dataclass
class RegistryRepositoryStub:
    revisions_by_id: dict[UUID, SimpleNamespace] = field(default_factory=dict)
    latest_revision_by_agent: dict[UUID, SimpleNamespace] = field(default_factory=dict)

    async def get_revision_by_id(self, revision_id: UUID) -> SimpleNamespace | None:
        return self.revisions_by_id.get(revision_id)

    async def get_latest_revision(self, agent_id: UUID) -> SimpleNamespace | None:
        return self.latest_revision_by_agent.get(agent_id)


@dataclass
class RegistryPolicyStub:
    agents: dict[UUID, SimpleNamespace] = field(default_factory=dict)
    visibility_by_agent: dict[UUID, tuple[list[str], list[str]]] = field(default_factory=dict)
    repository: RegistryRepositoryStub = field(default_factory=RegistryRepositoryStub)

    async def get_agent(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        actor_id: UUID | None = None,
        requesting_agent_id: UUID | None = None,
    ) -> SimpleNamespace:
        del workspace_id, actor_id, requesting_agent_id
        return self.agents[agent_id]

    async def resolve_effective_visibility(
        self, agent_id: UUID, workspace_id: UUID
    ) -> SimpleNamespace:
        del workspace_id
        agent_patterns, tool_patterns = self.visibility_by_agent.get(agent_id, ([], []))
        return SimpleNamespace(
            agent_patterns=list(agent_patterns),
            tool_patterns=list(tool_patterns),
        )


@dataclass
class ReasoningClientStub:
    remaining_by_execution: dict[UUID, dict[str, Any]] = field(default_factory=dict)

    async def get_remaining_budget(self, execution_id: UUID) -> dict[str, Any]:
        return self.remaining_by_execution.get(
            execution_id,
            {"remaining_tool_invocations": 1},
        )


@dataclass
class MemoryServiceStub:
    known_namespaces: set[str] = field(default_factory=set)
    contradictory_hashes: set[tuple[str, str]] = field(default_factory=set)

    async def namespace_exists(self, workspace_id: UUID, target_namespace: str) -> bool:
        del workspace_id
        return target_namespace in self.known_namespaces

    async def check_contradiction(self, content_hash: str, target_namespace: str) -> bool:
        return (content_hash, target_namespace) in self.contradictory_hashes


@dataclass
class InMemoryPolicyRepository:
    session: RecorderSession = field(default_factory=RecorderSession)
    policies: dict[UUID, PolicyPolicy] = field(default_factory=dict)
    versions_by_policy: dict[UUID, list[PolicyVersion]] = field(default_factory=dict)
    version_by_id: dict[UUID, PolicyVersion] = field(default_factory=dict)
    attachments: dict[UUID, PolicyAttachment] = field(default_factory=dict)
    blocked_records: dict[UUID, PolicyBlockedActionRecord] = field(default_factory=dict)
    bundle_cache: dict[str, PolicyBundleCache] = field(default_factory=dict)

    async def create(self, policy: PolicyPolicy) -> PolicyPolicy:
        stamp(policy)
        self.policies[policy.id] = policy
        self.versions_by_policy.setdefault(policy.id, [])
        await self.session.flush()
        return policy

    async def create_version(self, version: PolicyVersion) -> PolicyVersion:
        stamp(version)
        self.version_by_id[version.id] = version
        bucket = self.versions_by_policy.setdefault(version.policy_id, [])
        bucket.append(version)
        bucket.sort(key=lambda item: item.version_number)
        policy = self.policies.get(version.policy_id)
        if policy is not None:
            version.policy = policy
            policy.versions = list(bucket)
        await self.session.flush()
        return version

    async def get_by_id(self, policy_id: UUID) -> PolicyPolicy | None:
        return self.policies.get(policy_id)

    async def list_with_filters(
        self,
        *,
        scope_type: PolicyScopeType | None,
        status: PolicyStatus | None,
        workspace_id: UUID | None,
        offset: int,
        limit: int,
        allowed_ids: set[UUID] | None = None,
    ) -> tuple[list[PolicyPolicy], int]:
        items = [
            policy
            for policy in self.policies.values()
            if (scope_type is None or policy.scope_type == scope_type)
            and (status is None or policy.status == status)
            and (workspace_id is None or policy.workspace_id == workspace_id)
            and (allowed_ids is None or policy.id in allowed_ids)
        ]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return items[offset : offset + limit], len(items)

    async def get_versions(self, policy_id: UUID) -> list[PolicyVersion]:
        return list(self.versions_by_policy.get(policy_id, []))

    async def get_version_by_number(
        self, policy_id: UUID, version_number: int
    ) -> PolicyVersion | None:
        return next(
            (
                version
                for version in self.versions_by_policy.get(policy_id, [])
                if version.version_number == version_number
            ),
            None,
        )

    async def get_policy_version(self, version_id: UUID) -> PolicyVersion | None:
        return self.version_by_id.get(version_id)

    async def create_attachment(self, attachment: PolicyAttachment) -> PolicyAttachment:
        stamp(attachment)
        attachment.policy = self.policies[attachment.policy_id]
        attachment.policy_version = self.version_by_id[attachment.policy_version_id]
        self.attachments[attachment.id] = attachment
        attachment.policy.attachments.append(attachment)
        await self.session.flush()
        return attachment

    async def get_attachment(
        self, attachment_id: UUID, policy_id: UUID | None = None
    ) -> PolicyAttachment | None:
        attachment = self.attachments.get(attachment_id)
        if attachment is None:
            return None
        if policy_id is not None and attachment.policy_id != policy_id:
            return None
        return attachment

    async def find_active_attachment(
        self,
        *,
        policy_id: UUID,
        target_type: AttachmentTargetType,
        target_id: str | None,
    ) -> PolicyAttachment | None:
        return next(
            (
                attachment
                for attachment in self.attachments.values()
                if attachment.policy_id == policy_id
                and attachment.target_type == target_type
                and attachment.target_id == target_id
                and attachment.is_active
            ),
            None,
        )

    async def list_attachments(self, policy_id: UUID) -> list[PolicyAttachment]:
        return [
            attachment
            for attachment in self.attachments.values()
            if attachment.policy_id == policy_id and attachment.is_active
        ]

    async def deactivate_attachment(self, attachment: PolicyAttachment) -> None:
        attachment.is_active = False
        attachment.deactivated_at = datetime.now(UTC)
        await self.session.flush()

    async def deactivate_attachments_for_policy(self, policy_id: UUID) -> None:
        for attachment in await self.list_attachments(policy_id):
            attachment.is_active = False
            attachment.deactivated_at = datetime.now(UTC)
        await self.session.flush()

    async def get_all_applicable_attachments(
        self,
        *,
        workspace_id: UUID,
        agent_revision_id: str | None = None,
        deployment_id: str | None = None,
        execution_id: str | None = None,
    ) -> list[PolicyAttachment]:
        matched: list[PolicyAttachment] = []
        for attachment in self.attachments.values():
            policy = self.policies[attachment.policy_id]
            if not attachment.is_active or policy.status != PolicyStatus.active:
                continue
            if (
                attachment.target_type is AttachmentTargetType.global_scope
                and attachment.target_id is None
            ):
                matched.append(attachment)
            elif (
                attachment.target_type is AttachmentTargetType.workspace
                and attachment.target_id == str(workspace_id)
            ):
                matched.append(attachment)
            elif (
                attachment.target_type is AttachmentTargetType.agent_revision
                and agent_revision_id is not None
                and attachment.target_id == agent_revision_id
            ):
                matched.append(attachment)
            elif (
                attachment.target_type is AttachmentTargetType.deployment
                and deployment_id is not None
                and attachment.target_id == deployment_id
            ):
                matched.append(attachment)
            elif (
                attachment.target_type is AttachmentTargetType.execution
                and execution_id is not None
                and attachment.target_id == execution_id
            ):
                matched.append(attachment)
        matched.sort(key=lambda item: (item.created_at, item.id))
        return matched

    async def create_blocked_action_record(
        self, record: PolicyBlockedActionRecord
    ) -> PolicyBlockedActionRecord:
        stamp(record)
        self.blocked_records[record.id] = record
        await self.session.flush()
        return record

    async def list_blocked_action_records(
        self,
        *,
        agent_id: UUID | None = None,
        enforcement_component: EnforcementComponent | None = None,
        workspace_id: UUID | None = None,
        execution_id: UUID | None = None,
        since: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[PolicyBlockedActionRecord], int]:
        items = [
            record
            for record in self.blocked_records.values()
            if (agent_id is None or record.agent_id == agent_id)
            and (
                enforcement_component is None
                or record.enforcement_component == enforcement_component
            )
            and (workspace_id is None or record.workspace_id == workspace_id)
            and (execution_id is None or record.execution_id == execution_id)
            and (since is None or record.created_at >= since)
        ]
        items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return items[offset : offset + limit], len(items)

    async def get_blocked_action_record(self, record_id: UUID) -> PolicyBlockedActionRecord | None:
        return self.blocked_records.get(record_id)

    async def get_bundle_cache(self, fingerprint: str) -> PolicyBundleCache | None:
        cached = self.bundle_cache.get(fingerprint)
        if cached is None:
            return None
        if cached.expires_at <= datetime.now(UTC):
            return None
        return cached

    async def upsert_bundle_cache(self, cache: PolicyBundleCache) -> PolicyBundleCache:
        stamp(cache)
        self.bundle_cache[cache.fingerprint] = cache
        await self.session.flush()
        return cache


def build_policy_service_app(service: Any) -> FastAPI:
    app = FastAPI()
    app.include_router(policies_router)

    async def _policy_service_override() -> Any:
        return service

    async def _current_user_override() -> dict[str, Any]:
        return {
            "sub": str(uuid4()),
            "roles": ["platform_admin"],
        }

    app.dependency_overrides[get_policy_service] = _policy_service_override
    app.dependency_overrides[get_current_user] = _current_user_override
    return app


def build_cached_bundle(bundle: EnforcementBundle) -> bytes:
    return json.dumps(bundle.model_dump(mode="json")).encode("utf-8")


def build_policy_settings(**overrides: Any) -> PlatformSettings:
    return PlatformSettings(**overrides)


def build_bundle_cache_record(
    *,
    fingerprint: str,
    bundle: EnforcementBundle,
    expires_in_seconds: int = 300,
) -> PolicyBundleCache:
    return stamp(
        PolicyBundleCache(
            fingerprint=fingerprint,
            bundle_data=bundle.model_dump(mode="json"),
            source_version_ids=list(bundle.manifest.source_version_ids),
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
        )
    )


def build_execute_result(one: Any = None, many: list[Any] | None = None) -> ExecuteResultStub:
    return ExecuteResultStub(one=one, many=many or [])


def build_fake_redis() -> tuple[MemoryRedis, FakeAsyncRedisClient]:
    memory = MemoryRedis()
    return memory, FakeAsyncRedisClient(memory)
