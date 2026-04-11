from __future__ import annotations

import time
from dataclasses import dataclass
from platform.context_engineering.schemas import ContextElement
from typing import Any
from uuid import UUID

_CLASSIFICATION_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


@dataclass(slots=True)
class _PolicyCacheEntry:
    policies: list[Any]
    expires_at: float


class PrivacyFilter:
    def __init__(
        self,
        *,
        policies_service: Any | None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self.policies_service = policies_service
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[tuple[UUID, str], _PolicyCacheEntry] = {}

    async def filter(
        self,
        elements: list[ContextElement],
        agent_fqn: str,
        workspace_id: UUID,
        privacy_overrides: dict[str, Any] | None = None,
    ) -> tuple[list[ContextElement], list[dict[str, Any]]]:
        policies = await self._get_policies(workspace_id, agent_fqn)
        allowed = self._resolve_allowed_classifications(
            policies,
            agent_fqn,
            privacy_overrides or {},
        )
        excluded_sources = {
            value
            for value in (privacy_overrides or {}).get("excluded_source_types", [])
            if isinstance(value, str)
        }
        allowed_elements: list[ContextElement] = []
        exclusions: list[dict[str, Any]] = []
        for element in elements:
            if element.source_type.value in excluded_sources:
                exclusions.append(
                    {
                        "element_id": str(element.id),
                        "reason": "source_type_excluded",
                        "policy_id": None,
                    }
                )
                continue
            classification = (element.data_classification or "public").strip().lower()
            if classification in allowed or self._is_rank_allowed(classification, allowed):
                allowed_elements.append(element)
                continue
            exclusions.append(
                {
                    "element_id": str(element.id),
                    "reason": f"classification_not_authorized:{classification}",
                    "policy_id": self._first_policy_id(policies),
                }
            )
        return allowed_elements, exclusions

    async def _get_policies(self, workspace_id: UUID, agent_fqn: str) -> list[Any]:
        if self.policies_service is None or not hasattr(
            self.policies_service,
            "get_active_context_policies",
        ):
            return []
        cache_key = (workspace_id, agent_fqn)
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached is not None and cached.expires_at > now:
            return cached.policies
        policies = await self.policies_service.get_active_context_policies(workspace_id, agent_fqn)
        normalized = list(policies or [])
        self._cache[cache_key] = _PolicyCacheEntry(
            policies=normalized,
            expires_at=now + self.cache_ttl_seconds,
        )
        return normalized

    def _resolve_allowed_classifications(
        self,
        policies: list[Any],
        agent_fqn: str,
        privacy_overrides: dict[str, Any],
    ) -> set[str]:
        explicit_allowed = privacy_overrides.get("allowed_classifications")
        if isinstance(explicit_allowed, list) and explicit_allowed:
            return {str(item).strip().lower() for item in explicit_allowed if str(item).strip()}
        if not policies:
            return set(_CLASSIFICATION_RANK)

        allowed: set[str] = set()
        for policy in policies:
            allowed_fqns = self._string_list(policy, "allowed_agent_fqns") or self._string_list(
                policy,
                "agent_fqns",
            )
            if allowed_fqns and agent_fqn not in allowed_fqns and "*" not in allowed_fqns:
                continue
            policy_allowed = self._string_list(policy, "allowed_classifications")
            if policy_allowed:
                allowed.update(policy_allowed)
                continue
            action = str(self._get(policy, "action", "include")).strip().lower()
            if action != "include":
                continue
            level = (
                str(
                    self._get(
                        policy, "classification", self._get(policy, "data_classification", "public")
                    )
                )
                .strip()
                .lower()
            )
            max_rank = _CLASSIFICATION_RANK.get(level, 0)
            allowed.update(name for name, rank in _CLASSIFICATION_RANK.items() if rank <= max_rank)
        return allowed or {"public"}

    def _is_rank_allowed(self, classification: str, allowed: set[str]) -> bool:
        allowed_ranks = [
            _CLASSIFICATION_RANK[item] for item in allowed if item in _CLASSIFICATION_RANK
        ]
        if not allowed_ranks:
            return classification == "public"
        return _CLASSIFICATION_RANK.get(classification, 0) <= max(allowed_ranks)

    def _first_policy_id(self, policies: list[Any]) -> str | None:
        for policy in policies:
            identifier = self._get(policy, "policy_id", self._get(policy, "id"))
            if identifier is not None:
                return str(identifier)
        return None

    def _string_list(self, source: Any, name: str) -> list[str]:
        raw = self._get(source, name, [])
        if not isinstance(raw, list):
            return []
        return [str(item).strip().lower() for item in raw if str(item).strip()]

    def _get(self, source: Any, name: str, default: Any = None) -> Any:
        if isinstance(source, dict):
            return source.get(name, default)
        return getattr(source, name, default)
