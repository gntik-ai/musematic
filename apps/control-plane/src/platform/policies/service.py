from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from platform.common.events.envelope import CorrelationContext
from platform.policies.compiler import GovernanceCompiler
from platform.policies.events import (
    GateAllowedEvent,
    GateBlockedEvent,
    PolicyArchivedEvent,
    PolicyAttachedEvent,
    PolicyCreatedEvent,
    PolicyDetachedEvent,
    PolicyEventType,
    PolicyUpdatedEvent,
    publish_gate_allowed,
    publish_gate_blocked,
    publish_policy_event,
)
from platform.policies.exceptions import PolicyAttachmentError, PolicyNotFoundError
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
from platform.policies.repository import PolicyRepository
from platform.policies.schemas import (
    EffectivePolicyResponse,
    EnforcementBundle,
    MaturityGateLevel,
    MaturityGateListResponse,
    PolicyAttachmentListResponse,
    PolicyAttachRequest,
    PolicyAttachResponse,
    PolicyBlockedActionListResponse,
    PolicyBlockedActionRecordResponse,
    PolicyConflict,
    PolicyCreate,
    PolicyListResponse,
    PolicyResponse,
    PolicyRuleProvenance,
    PolicyUpdate,
    PolicyVersionListResponse,
    PolicyVersionResponse,
    PolicyWithVersionResponse,
    ResolvedRule,
)
from typing import Any, cast
from uuid import UUID, uuid4

_SCOPE_LEVELS: dict[AttachmentTargetType, int] = {
    AttachmentTargetType.global_scope: 0,
    AttachmentTargetType.deployment: 1,
    AttachmentTargetType.workspace: 2,
    AttachmentTargetType.agent_revision: 3,
    AttachmentTargetType.execution: 4,
    AttachmentTargetType.fleet: 4,
}


class PolicyService:
    def __init__(
        self,
        *,
        repository: PolicyRepository,
        settings: Any,
        producer: Any | None,
        redis_client: Any | None,
        registry_service: Any | None,
        workspaces_service: Any | None,
        reasoning_client: Any | None = None,
        compiler: GovernanceCompiler | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.redis_client = redis_client
        self.registry_service = registry_service
        self.workspaces_service = workspaces_service
        self.reasoning_client = reasoning_client
        self.compiler = compiler or GovernanceCompiler()

    async def register_simulation_policy_bundle(
        self,
        simulation_run_id: UUID,
        rules: list[dict[str, Any]],
        workspace_id: UUID,
    ) -> str:
        payload = {
            "simulation_run_id": str(simulation_run_id),
            "workspace_id": str(workspace_id),
            "rules": rules,
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        fingerprint = hashlib.sha256(encoded).hexdigest()
        if self.redis_client is not None:
            await self.redis_client.set(
                f"policy:simulation:{fingerprint}",
                encoded,
                ttl=24 * 60 * 60,
            )
        return fingerprint

    async def deregister_simulation_policy_bundle(self, bundle_fingerprint: str) -> None:
        if self.redis_client is not None:
            await self.redis_client.delete(f"policy:simulation:{bundle_fingerprint}")

    async def create_policy(
        self, data: PolicyCreate, created_by: UUID
    ) -> PolicyWithVersionResponse:
        policy = await self.repository.create(
            PolicyPolicy(
                name=data.name,
                description=data.description,
                scope_type=data.scope_type,
                status=PolicyStatus.active,
                workspace_id=data.workspace_id,
                created_by=created_by,
                updated_by=created_by,
            )
        )
        version = await self.repository.create_version(
            PolicyVersion(
                policy_id=policy.id,
                version_number=1,
                rules=data.rules.model_dump(mode="json"),
                change_summary=data.change_summary,
                created_by=created_by,
            )
        )
        policy.current_version_id = version.id
        policy.current_version = version
        await self.repository.session.flush()
        await publish_policy_event(
            self.producer,
            PolicyEventType.policy_created,
            PolicyCreatedEvent(
                policy_id=policy.id,
                policy_name=policy.name,
                scope_type=policy.scope_type.value,
                version_id=version.id,
                workspace_id=policy.workspace_id,
                created_by=created_by,
            ),
            self._correlation(workspace_id=policy.workspace_id),
        )
        return self._policy_with_version_response(policy, version)

    async def update_policy(
        self,
        policy_id: UUID,
        data: PolicyUpdate,
        updated_by: UUID,
    ) -> PolicyWithVersionResponse:
        policy = await self._get_policy_or_raise(policy_id)
        versions = await self.repository.get_versions(policy_id)
        current_version = policy.current_version or versions[-1]
        if data.name is not None:
            policy.name = data.name
        if "description" in data.model_fields_set:
            policy.description = data.description
        policy.updated_by = updated_by
        version = await self.repository.create_version(
            PolicyVersion(
                policy_id=policy.id,
                version_number=(versions[-1].version_number if versions else 0) + 1,
                rules=(
                    data.rules.model_dump(mode="json")
                    if data.rules is not None
                    else dict(current_version.rules)
                ),
                change_summary=data.change_summary,
                created_by=updated_by,
            )
        )
        policy.current_version_id = version.id
        policy.current_version = version
        await self.repository.session.flush()
        await publish_policy_event(
            self.producer,
            PolicyEventType.policy_updated,
            PolicyUpdatedEvent(
                policy_id=policy.id,
                version_id=version.id,
                version_number=version.version_number,
                updated_by=updated_by,
            ),
            self._correlation(workspace_id=policy.workspace_id),
        )
        return self._policy_with_version_response(policy, version)

    async def archive_policy(self, policy_id: UUID, archived_by: UUID) -> PolicyResponse:
        policy = await self._get_policy_or_raise(policy_id)
        policy.status = PolicyStatus.archived
        policy.updated_by = archived_by
        await self.repository.deactivate_attachments_for_policy(policy_id)
        await self.repository.session.flush()
        await publish_policy_event(
            self.producer,
            PolicyEventType.policy_archived,
            PolicyArchivedEvent(policy_id=policy.id, archived_by=archived_by),
            self._correlation(workspace_id=policy.workspace_id),
        )
        return PolicyResponse.model_validate(policy)

    async def get_policy(self, policy_id: UUID) -> PolicyWithVersionResponse:
        policy = await self._get_policy_or_raise(policy_id)
        version = policy.current_version
        return self._policy_with_version_response(policy, version)

    async def list_policies(
        self,
        *,
        scope_type: PolicyScopeType | None,
        status: PolicyStatus | None,
        workspace_id: UUID | None,
        page: int,
        page_size: int,
    ) -> PolicyListResponse:
        items, total = await self.repository.list_with_filters(
            scope_type=scope_type,
            status=status,
            workspace_id=workspace_id,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return PolicyListResponse(
            items=[PolicyResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_version_history(self, policy_id: UUID) -> PolicyVersionListResponse:
        await self._get_policy_or_raise(policy_id)
        versions = await self.repository.get_versions(policy_id)
        return PolicyVersionListResponse(
            items=[PolicyVersionResponse.model_validate(version) for version in versions],
            total=len(versions),
        )

    async def get_version_by_number(
        self, policy_id: UUID, version_number: int
    ) -> PolicyVersionResponse:
        version = await self.repository.get_version_by_number(policy_id, version_number)
        if version is None:
            raise PolicyNotFoundError(f"{policy_id}/versions/{version_number}")
        return PolicyVersionResponse.model_validate(version)

    async def attach_policy(
        self,
        policy_id: UUID,
        request: PolicyAttachRequest,
        created_by: UUID,
    ) -> PolicyAttachResponse:
        policy = await self._get_policy_or_raise(policy_id)
        await self._validate_attachment_target(
            request.target_type, request.target_id, policy.workspace_id
        )
        existing = await self.repository.find_active_attachment(
            policy_id=policy_id,
            target_type=request.target_type,
            target_id=request.target_id,
        )
        if existing is not None:
            raise PolicyAttachmentError(
                "Policy is already attached to this target", code="POLICY_ALREADY_ATTACHED"
            )
        version = (
            await self.repository.get_policy_version(request.policy_version_id)
            if request.policy_version_id is not None
            else policy.current_version
        )
        if version is None or version.policy_id != policy.id:
            raise PolicyAttachmentError(
                "Policy version is not valid for this policy", code="POLICY_VERSION_INVALID"
            )
        attachment = await self.repository.create_attachment(
            PolicyAttachment(
                policy_id=policy.id,
                policy_version_id=version.id,
                target_type=request.target_type,
                target_id=request.target_id,
                created_by=created_by,
                is_active=True,
            )
        )
        await publish_policy_event(
            self.producer,
            PolicyEventType.policy_attached,
            PolicyAttachedEvent(
                policy_id=policy.id,
                attachment_id=attachment.id,
                target_type=attachment.target_type.value,
                target_id=attachment.target_id,
            ),
            self._correlation(workspace_id=policy.workspace_id),
        )
        return PolicyAttachResponse.model_validate(attachment)

    async def detach_policy(self, policy_id: UUID, attachment_id: UUID) -> None:
        attachment = await self.repository.get_attachment(attachment_id, policy_id)
        if attachment is None:
            raise PolicyAttachmentError(
                "Attachment was not found", code="POLICY_ATTACHMENT_NOT_FOUND"
            )
        await self.repository.deactivate_attachment(attachment)
        await publish_policy_event(
            self.producer,
            PolicyEventType.policy_detached,
            PolicyDetachedEvent(
                policy_id=attachment.policy_id,
                attachment_id=attachment.id,
                target_type=attachment.target_type.value,
                target_id=attachment.target_id,
            ),
            self._correlation(),
        )

    async def list_attachments(self, policy_id: UUID) -> PolicyAttachmentListResponse:
        await self._get_policy_or_raise(policy_id)
        attachments = await self.repository.list_attachments(policy_id)
        return PolicyAttachmentListResponse(
            items=[PolicyAttachResponse.model_validate(item) for item in attachments],
            total=len(attachments),
        )

    async def get_effective_policy(
        self,
        agent_id: UUID,
        workspace_id: UUID,
        *,
        execution_id: UUID | None = None,
    ) -> EffectivePolicyResponse:
        _, versions, conflicts = await self._load_applicable_versions(
            agent_id=agent_id,
            workspace_id=workspace_id,
            execution_id=execution_id,
        )
        resolved_rules: list[ResolvedRule] = []
        seen_keys: dict[str, tuple[int, PolicyScopeType, dict[str, Any], PolicyRuleProvenance]] = {}
        source_policies: set[UUID] = set()
        for version in versions:
            source_policies.add(version.policy_id)
            scope_level = int(getattr(version, "_scope_level", 0))
            scope_type = getattr(version, "_scope_type", PolicyScopeType.global_scope)
            scope_target_id = getattr(version, "_scope_target_id", None)
            for rule in version.rules.get("enforcement_rules", []):
                provenance = PolicyRuleProvenance(
                    rule_id=str(rule.get("id") or version.id),
                    policy_id=version.policy_id,
                    version_id=version.id,
                    scope_level=scope_level,
                    scope_type=scope_type,
                    scope_target_id=scope_target_id,
                )
                for pattern in rule.get("tool_patterns", []) or []:
                    key = str(pattern)
                    existing = seen_keys.get(key)
                    current_rule = dict(rule)
                    current_rule["tool_patterns"] = [key]
                    current_action = str(current_rule.get("action", "deny"))
                    if existing is None or scope_level >= existing[0]:
                        if existing is not None and existing[2].get("action") != current_action:
                            conflicts.append(
                                PolicyConflict(
                                    rule_id=provenance.rule_id,
                                    winner_scope=scope_type,
                                    loser_scope=existing[1],
                                    resolution=(
                                        "deny_wins"
                                        if scope_level == existing[0]
                                        and "deny"
                                        in {current_action, str(existing[2].get("action", "deny"))}
                                        else "more_specific_scope_wins"
                                    ),
                                )
                            )
                        seen_keys[key] = (scope_level, scope_type, current_rule, provenance)
        for _, _, rule, provenance in seen_keys.values():
            resolved_rules.append(ResolvedRule(rule=rule, provenance=provenance))
        return EffectivePolicyResponse(
            agent_id=agent_id,
            resolved_rules=sorted(
                resolved_rules,
                key=lambda item: (item.provenance.scope_level, item.rule.get("id", "")),
            ),
            conflicts=conflicts,
            source_policies=sorted(source_policies, key=str),
        )

    async def get_enforcement_bundle(
        self,
        agent_id: UUID,
        workspace_id: UUID,
        *,
        execution_id: UUID | None = None,
    ) -> EnforcementBundle:
        revision_id, versions, _ = await self._load_applicable_versions(
            agent_id=agent_id,
            workspace_id=workspace_id,
            execution_id=execution_id,
        )
        compiled_bundle = self.compiler.compile_bundle(versions, agent_id, workspace_id)
        fingerprint = compiled_bundle.fingerprint
        cache_key = f"policy:bundle:{fingerprint}"
        cached = await self._redis_get_json(cache_key)
        if cached is not None:
            cached_bundle = EnforcementBundle.model_validate(cached)
            cached_bundle.set_step_maps(
                allowed=compiled_bundle.step_allowed_tool_patterns,
                denied=compiled_bundle.step_denied_tool_patterns,
            )
            return cached_bundle

        bundle = compiled_bundle
        await self._redis_set_json(cache_key, bundle.model_dump(mode="json"), ttl=300)
        await self._register_bundle_key(agent_id, revision_id, cache_key)
        await self.repository.upsert_bundle_cache(
            PolicyBundleCache(
                fingerprint=fingerprint,
                bundle_data=bundle.model_dump(mode="json"),
                source_version_ids=[version.id for version in versions],
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        return bundle

    async def invalidate_bundle(self, agent_id: UUID) -> None:
        await self._invalidate_bundle_index(f"policy:bundle_keys:{agent_id}")

    async def invalidate_bundle_by_revision(self, revision_id: str) -> None:
        await self._invalidate_bundle_index(f"policy:bundle_keys:revision:{revision_id}")

    async def list_blocked_action_records(
        self,
        *,
        agent_id: UUID | None,
        enforcement_component: EnforcementComponent | None,
        workspace_id: UUID | None,
        execution_id: UUID | None,
        since: datetime | None,
        page: int,
        page_size: int,
    ) -> PolicyBlockedActionListResponse:
        items, total = await self.repository.list_blocked_action_records(
            agent_id=agent_id,
            enforcement_component=enforcement_component,
            workspace_id=workspace_id,
            execution_id=execution_id,
            since=since,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return PolicyBlockedActionListResponse(
            items=[PolicyBlockedActionRecordResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_blocked_action_record(self, record_id: UUID) -> PolicyBlockedActionRecordResponse:
        record = await self.repository.get_blocked_action_record(record_id)
        if record is None:
            raise PolicyNotFoundError(record_id)
        return PolicyBlockedActionRecordResponse.model_validate(record)

    async def get_maturity_gates(self) -> MaturityGateListResponse:
        levels: dict[int, set[str]] = {}
        active, total = await self.repository.list_with_filters(
            scope_type=PolicyScopeType.global_scope,
            status=PolicyStatus.active,
            workspace_id=None,
            offset=0,
            limit=100,
        )
        for policy in active:
            if policy.current_version is None:
                continue
            for gate in policy.current_version.rules.get("maturity_gate_rules", []):
                level = int(gate.get("min_maturity_level", 0))
                bucket = levels.setdefault(level, set())
                bucket.update(
                    str(item).strip()
                    for item in gate.get("capability_patterns", [])
                    if str(item).strip()
                )
        del total
        return MaturityGateListResponse(
            levels=[
                MaturityGateLevel(level=level, capabilities=sorted(capabilities))
                for level, capabilities in sorted(levels.items())
            ]
        )

    async def get_active_context_policies(
        self, workspace_id: UUID, agent_fqn: str
    ) -> list[dict[str, Any]]:
        del agent_fqn
        items, _ = await self.repository.list_with_filters(
            scope_type=None,
            status=PolicyStatus.active,
            workspace_id=workspace_id,
            offset=0,
            limit=100,
        )
        policies: list[dict[str, Any]] = []
        for policy in items:
            if policy.current_version is None:
                continue
            rules = dict(policy.current_version.rules)
            if rules.get("allowed_classifications") or rules.get("allowed_agent_fqns"):
                policies.append(
                    {
                        "policy_id": str(policy.id),
                        **rules,
                    }
                )
        return policies

    async def create_blocked_record(
        self,
        *,
        agent_id: UUID,
        agent_fqn: str,
        enforcement_component: EnforcementComponent,
        action_type: str,
        target: str,
        block_reason: str,
        workspace_id: UUID | None,
        execution_id: UUID | None,
        policy_rule_ref: dict[str, Any] | None,
    ) -> PolicyBlockedActionRecord:
        record = await self.repository.create_blocked_action_record(
            PolicyBlockedActionRecord(
                agent_id=agent_id,
                agent_fqn=agent_fqn,
                enforcement_component=enforcement_component,
                action_type=action_type,
                target=target,
                block_reason=block_reason,
                policy_rule_ref=policy_rule_ref,
                workspace_id=workspace_id,
                execution_id=execution_id,
            )
        )
        await publish_gate_blocked(
            self.producer,
            GateBlockedEvent(
                agent_id=agent_id,
                agent_fqn=agent_fqn,
                enforcement_component=enforcement_component.value,
                action_type=action_type,
                target=target,
                block_reason=block_reason,
                execution_id=execution_id,
                workspace_id=workspace_id,
                policy_rule_ref=policy_rule_ref,
            ),
            self._correlation(workspace_id=workspace_id, execution_id=execution_id),
        )
        return record

    async def publish_allowed_event(
        self,
        *,
        agent_id: UUID,
        agent_fqn: str,
        target: str,
        workspace_id: UUID | None,
        execution_id: UUID | None,
    ) -> None:
        await publish_gate_allowed(
            self.producer,
            GateAllowedEvent(
                agent_id=agent_id,
                agent_fqn=agent_fqn,
                target=target,
                execution_id=execution_id,
                workspace_id=workspace_id,
            ),
            self._correlation(workspace_id=workspace_id, execution_id=execution_id),
        )

    async def get_visibility_filter(self, agent_id: UUID, workspace_id: UUID) -> Any:
        if self.registry_service is not None and hasattr(
            self.registry_service, "resolve_effective_visibility"
        ):
            return await self.registry_service.resolve_effective_visibility(agent_id, workspace_id)
        return type(
            "VisibilityFilter",
            (),
            {"agent_patterns": [], "tool_patterns": []},
        )()

    async def _load_applicable_versions(
        self,
        *,
        agent_id: UUID,
        workspace_id: UUID,
        execution_id: UUID | None = None,
    ) -> tuple[str | None, list[PolicyVersion], list[PolicyConflict]]:
        agent_revision_id = await self._resolve_agent_revision_id(agent_id, workspace_id)
        attachments = await self.repository.get_all_applicable_attachments(
            workspace_id=workspace_id,
            agent_revision_id=agent_revision_id,
            execution_id=str(execution_id) if execution_id is not None else None,
        )
        versions: list[PolicyVersion] = []
        conflicts: list[PolicyConflict] = []
        for attachment in attachments:
            version = attachment.policy_version
            version_any = cast(Any, version)
            version_any._scope_level = _SCOPE_LEVELS.get(attachment.target_type, 0)
            scope_type = {
                AttachmentTargetType.global_scope: PolicyScopeType.global_scope,
                AttachmentTargetType.deployment: PolicyScopeType.deployment,
                AttachmentTargetType.workspace: PolicyScopeType.workspace,
                AttachmentTargetType.agent_revision: PolicyScopeType.agent,
                AttachmentTargetType.execution: PolicyScopeType.execution,
                AttachmentTargetType.fleet: PolicyScopeType.execution,
            }[attachment.target_type]
            version_any._scope_type = scope_type
            version_any._scope_target_id = attachment.target_id
            versions.append(version)
        versions.sort(key=lambda item: (getattr(item, "_scope_level", 0), item.version_number))
        return agent_revision_id, versions, conflicts

    async def _resolve_agent_revision_id(self, agent_id: UUID, workspace_id: UUID) -> str | None:
        if self.registry_service is None:
            return str(agent_id)
        getter = getattr(self.registry_service, "get_agent", None)
        if callable(getter):
            try:
                profile = await getter(
                    workspace_id, agent_id, actor_id=None, requesting_agent_id=None
                )
            except TypeError:
                profile = await getter(workspace_id, agent_id)
            current_revision = getattr(profile, "current_revision", None)
            if current_revision is not None and getattr(current_revision, "id", None) is not None:
                return str(current_revision.id)
        repository = getattr(self.registry_service, "repository", None)
        if repository is not None and hasattr(repository, "get_latest_revision"):
            latest = await repository.get_latest_revision(agent_id)
            if latest is not None:
                return str(latest.id)
        return str(agent_id)

    async def _validate_attachment_target(
        self,
        target_type: AttachmentTargetType,
        target_id: str | None,
        workspace_id: UUID | None,
    ) -> None:
        if target_type is AttachmentTargetType.global_scope:
            if target_id is not None:
                raise PolicyAttachmentError("Global attachments must not include a target_id")
            return
        if target_id is None:
            raise PolicyAttachmentError("Attachment target_id is required for this target type")
        if target_type is AttachmentTargetType.workspace and self.workspaces_service is not None:
            repository = getattr(self.workspaces_service, "repo", None)
            if repository is not None and hasattr(repository, "get_workspace_by_id_any"):
                workspace = await repository.get_workspace_by_id_any(UUID(target_id))
                if workspace is None:
                    raise PolicyAttachmentError("Workspace attachment target does not exist")
        if target_type is AttachmentTargetType.agent_revision and self.registry_service is not None:
            repository = getattr(self.registry_service, "repository", None) or getattr(
                self.registry_service, "repo", None
            )
            if repository is not None and hasattr(repository, "get_revision_by_id"):
                revision = await repository.get_revision_by_id(UUID(target_id))
                if revision is None:
                    raise PolicyAttachmentError("Agent revision attachment target does not exist")
        del workspace_id

    async def _redis_get_json(self, key: str) -> dict[str, Any] | None:
        if self.redis_client is None:
            return None
        raw = await self.redis_client.get(key)
        if raw is None:
            return None
        import json

        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        return cast(dict[str, Any], payload)

    async def _redis_set_json(self, key: str, payload: dict[str, Any], *, ttl: int) -> None:
        if self.redis_client is None:
            return
        import json

        await self.redis_client.set(key, json.dumps(payload).encode("utf-8"), ttl=ttl)

    async def _register_bundle_key(
        self, agent_id: UUID, revision_id: str | None, cache_key: str
    ) -> None:
        if self.redis_client is None:
            return
        client = await self.redis_client._get_client()
        if hasattr(client, "sadd"):
            await client.sadd(f"policy:bundle_keys:{agent_id}", cache_key)
            if revision_id is not None:
                await client.sadd(f"policy:bundle_keys:revision:{revision_id}", cache_key)

    async def _invalidate_bundle_index(self, index_key: str) -> None:
        if self.redis_client is None:
            return
        client = await self.redis_client._get_client()
        keys: set[str] = set()
        if hasattr(client, "smembers"):
            keys = set(await client.smembers(index_key))
        for key in keys:
            await self.redis_client.delete(key)
        await self.redis_client.delete(index_key)

    async def _get_policy_or_raise(self, policy_id: UUID) -> PolicyPolicy:
        policy = await self.repository.get_by_id(policy_id)
        if policy is None:
            raise PolicyNotFoundError(policy_id)
        return policy

    @staticmethod
    def _policy_with_version_response(
        policy: PolicyPolicy,
        version: PolicyVersion | None,
    ) -> PolicyWithVersionResponse:
        response = PolicyWithVersionResponse.model_validate(policy)
        response.current_version = (
            PolicyVersionResponse.model_validate(version) if version is not None else None
        )
        return response

    @staticmethod
    def _correlation(
        *,
        workspace_id: UUID | None = None,
        execution_id: UUID | None = None,
    ) -> CorrelationContext:
        return CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=workspace_id,
            execution_id=execution_id,
        )
