from __future__ import annotations

from platform.common.exceptions import NotFoundError, ValidationError
from platform.model_catalog.models import ModelCatalogEntry, ModelFallbackPolicy
from platform.model_catalog.repository import ModelCatalogRepository
from platform.model_catalog.schemas import (
    FallbackPolicyCreate,
    FallbackPolicyListResponse,
    FallbackPolicyPatch,
    FallbackPolicyResponse,
)
from uuid import UUID

_TIER_RANK = {"tier1": 1, "tier2": 2, "tier3": 3}
_MAX_DEGRADATION = {"tier_equal": 0, "tier_plus_one": 1, "tier_plus_two": 2}


class FallbackPolicyService:
    def __init__(self, repository: ModelCatalogRepository) -> None:
        self.repository = repository

    async def create_policy(self, request: FallbackPolicyCreate) -> FallbackPolicyResponse:
        primary = await self._get_entry(request.primary_model_id)
        chain = await self._validated_chain(
            primary,
            request.fallback_chain,
            request.acceptable_quality_degradation,
        )
        policy = await self.repository.add(
            ModelFallbackPolicy(
                name=request.name,
                scope_type=request.scope_type,
                scope_id=request.scope_id,
                primary_model_id=primary.id,
                fallback_chain=[str(item.id) for item in chain],
                retry_count=request.retry_count,
                backoff_strategy=request.backoff_strategy,
                acceptable_quality_degradation=request.acceptable_quality_degradation,
                recovery_window_seconds=request.recovery_window_seconds,
            )
        )
        return FallbackPolicyResponse.model_validate(policy)

    async def resolve_policy_for_scope(
        self,
        *,
        workspace_id: UUID,
        agent_id: UUID | None,
        primary_model_id: UUID,
    ) -> FallbackPolicyResponse | None:
        policy = None
        if agent_id is not None:
            policy = await self.repository.get_fallback_policy_for_scope(
                scope_type="agent",
                scope_id=agent_id,
                primary_model_id=primary_model_id,
            )
        if policy is None:
            policy = await self.repository.get_fallback_policy_for_scope(
                scope_type="workspace",
                scope_id=workspace_id,
                primary_model_id=primary_model_id,
            )
        if policy is None:
            policy = await self.repository.get_fallback_policy_for_scope(
                scope_type="global",
                scope_id=None,
                primary_model_id=primary_model_id,
            )
        return None if policy is None else FallbackPolicyResponse.model_validate(policy)

    async def list_policies(
        self,
        *,
        primary_model_id: UUID | None = None,
        scope_type: str | None = None,
    ) -> FallbackPolicyListResponse:
        items = await self.repository.list_fallback_policies(
            primary_model_id=primary_model_id,
            scope_type=scope_type,
        )
        return FallbackPolicyListResponse(
            items=[FallbackPolicyResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def update_policy(
        self,
        policy_id: UUID,
        patch: FallbackPolicyPatch,
    ) -> FallbackPolicyResponse:
        policy = await self._get_policy(policy_id)
        updates = patch.model_dump(exclude_unset=True)
        degradation = updates.get(
            "acceptable_quality_degradation",
            policy.acceptable_quality_degradation,
        )
        if "fallback_chain" in updates:
            primary = await self._get_entry(policy.primary_model_id)
            chain = await self._validated_chain(primary, updates["fallback_chain"], degradation)
            updates["fallback_chain"] = [str(item.id) for item in chain]
        for field, value in updates.items():
            setattr(policy, field, value)
        if updates:
            await self.repository.session.flush()
        return FallbackPolicyResponse.model_validate(policy)

    async def delete_policy(self, policy_id: UUID) -> None:
        policy = await self._get_policy(policy_id)
        await self.repository.delete_fallback_policy(policy)

    async def _get_policy(self, policy_id: UUID) -> ModelFallbackPolicy:
        policy = await self.repository.get_fallback_policy(policy_id)
        if policy is None:
            raise NotFoundError("FALLBACK_POLICY_NOT_FOUND", "Fallback policy not found")
        return policy

    async def _get_entry(self, entry_id: UUID) -> ModelCatalogEntry:
        entry = await self.repository.get_entry(entry_id)
        if entry is None:
            raise NotFoundError("MODEL_CATALOG_ENTRY_NOT_FOUND", "Catalogue entry not found")
        return entry

    async def _entry_for_chain_item(self, chain_item: str) -> ModelCatalogEntry:
        try:
            return await self._get_entry(UUID(chain_item))
        except ValueError as exc:
            provider, separator, model_id = chain_item.partition(":")
            if not separator:
                raise ValidationError(
                    "FALLBACK_CHAIN_ITEM_INVALID",
                    "Fallback chain items must be catalogue entry UUIDs or provider:model_id.",
                ) from exc
            entry = await self.repository.get_entry_by_provider_model(provider, model_id)
            if entry is None:
                raise NotFoundError(
                    "MODEL_CATALOG_ENTRY_NOT_FOUND",
                    "Fallback chain entry not found",
                ) from exc
            return entry

    async def _validated_chain(
        self,
        primary: ModelCatalogEntry,
        chain_items: list[str],
        degradation: str,
    ) -> list[ModelCatalogEntry]:
        if primary.status == "blocked":
            raise ValidationError("PRIMARY_MODEL_BLOCKED", "Primary model is blocked")
        seen: set[UUID] = {primary.id}
        chain: list[ModelCatalogEntry] = []
        max_degradation = _MAX_DEGRADATION[degradation]
        primary_rank = _TIER_RANK[primary.quality_tier]
        for chain_item in chain_items:
            entry = await self._entry_for_chain_item(chain_item)
            if entry.id in seen:
                raise ValidationError(
                    "FALLBACK_POLICY_CYCLE",
                    "Fallback chain cannot include duplicates or the primary model.",
                )
            if entry.status == "blocked":
                raise ValidationError("FALLBACK_MODEL_BLOCKED", "Fallback model is blocked")
            if entry.context_window < primary.context_window:
                raise ValidationError(
                    "FALLBACK_CONTEXT_WINDOW_TOO_SMALL",
                    "Fallback context window must be at least the primary context window.",
                )
            if _TIER_RANK[entry.quality_tier] - primary_rank > max_degradation:
                raise ValidationError(
                    "FALLBACK_TIER_DEGRADATION_TOO_HIGH",
                    "Fallback model exceeds acceptable quality degradation.",
                )
            seen.add(entry.id)
            chain.append(entry)
        return chain
