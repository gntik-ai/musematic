from __future__ import annotations

import json
import re
import time
from platform.trust.events import (
    PreScreenerRuleSetActivatedPayload,
    TrustEventPublisher,
    make_correlation,
    utcnow,
)
from platform.trust.exceptions import PreScreenerError
from platform.trust.models import TrustSafetyPreScreenerRuleSet
from platform.trust.repository import TrustRepository
from platform.trust.schemas import (
    PreScreenerRuleSetCreate,
    PreScreenerRuleSetListResponse,
    PreScreenerRuleSetResponse,
    PreScreenResponse,
)
from typing import Any
from uuid import UUID


class SafetyPreScreenerService:
    def __init__(
        self,
        *,
        repository: TrustRepository,
        settings: Any,
        redis_client: Any,
        object_storage: Any,
        producer: Any | None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.redis_client = redis_client
        self.object_storage = object_storage
        self.events = TrustEventPublisher(producer)
        self._compiled_patterns: dict[str, re.Pattern[str]] = {}
        self._active_version: str | None = None

    async def screen(self, content: str, context_type: str) -> PreScreenResponse:
        del context_type
        started = time.perf_counter()
        for name, pattern in self._compiled_patterns.items():
            if pattern.search(content):
                return PreScreenResponse(
                    blocked=True,
                    matched_rule=name,
                    passed_to_full_pipeline=False,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    rule_set_version=self._active_version,
                )
        return PreScreenResponse(
            blocked=False,
            passed_to_full_pipeline=True,
            latency_ms=(time.perf_counter() - started) * 1000,
            rule_set_version=self._active_version,
        )

    async def load_active_rules(self) -> None:
        version_bytes = await self.redis_client.get("trust:prescreener:active_version")
        rule_set: TrustSafetyPreScreenerRuleSet | None = None
        if version_bytes is not None:
            try:
                version = int(version_bytes.decode("utf-8"))
                rule_set = await self.repository.get_rule_set_by_version(version)
            except ValueError:
                rule_set = None
        if rule_set is None:
            rule_set = await self.repository.get_active_prescreener_rule_set()
        if rule_set is None:
            self._compiled_patterns = {}
            self._active_version = None
            return
        bucket = self._bucket_name
        rules_raw = await self.object_storage.download_object(bucket, rule_set.rules_ref)
        rules = json.loads(rules_raw.decode("utf-8"))
        compiled: dict[str, re.Pattern[str]] = {}
        for item in rules:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            pattern = str(item.get("pattern") or "")
            if not name or not pattern:
                continue
            compiled[name] = re.compile(pattern, re.IGNORECASE)
        self._compiled_patterns = compiled
        self._active_version = str(rule_set.version)

    async def list_rule_sets(self) -> PreScreenerRuleSetListResponse:
        items = await self.repository.list_rule_sets()
        return PreScreenerRuleSetListResponse(
            items=[PreScreenerRuleSetResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def create_rule_set(self, data: PreScreenerRuleSetCreate) -> PreScreenerRuleSetResponse:
        version = await self.repository.next_rule_set_version()
        bucket = self._bucket_name
        rules_key = f"prescreener/{version}/rules.json"
        await self.object_storage.create_bucket_if_not_exists(bucket)
        await self.object_storage.upload_object(
            bucket,
            rules_key,
            json.dumps([rule.model_dump(mode="json") for rule in data.rules]).encode("utf-8"),
            content_type="application/json",
        )
        item = await self.repository.create_rule_set(
            TrustSafetyPreScreenerRuleSet(
                version=version,
                name=data.name,
                description=data.description,
                is_active=False,
                rules_ref=rules_key,
                rule_count=len(data.rules),
            )
        )
        return PreScreenerRuleSetResponse.model_validate(item)

    async def activate_rule_set(self, rule_set_id: UUID) -> PreScreenerRuleSetResponse:
        rule_set = await self.repository.get_rule_set(rule_set_id)
        if rule_set is None:
            raise PreScreenerError("Rule set not found", rule_set_id=rule_set_id)
        activated = await self.repository.set_active_rule_set(rule_set.id)
        await self.redis_client.set(
            "trust:prescreener:active_version",
            str(activated.version).encode("utf-8"),
        )
        await self.redis_client.set(
            f"trust:prescreener:rules:{activated.version}",
            activated.rules_ref.encode("utf-8"),
        )
        await self.load_active_rules()
        await self.events.publish_prescreener_rule_set_activated(
            PreScreenerRuleSetActivatedPayload(
                version=activated.version,
                rule_count=activated.rule_count,
                occurred_at=utcnow(),
            ),
            make_correlation(),
        )
        return PreScreenerRuleSetResponse.model_validate(activated)

    async def handle_rule_set_activated(self, event: dict[str, Any]) -> None:
        del event
        await self.load_active_rules()

    @property
    def _bucket_name(self) -> str:
        trust_settings = getattr(self.settings, "trust", None)
        return str(getattr(trust_settings, "evidence_bucket", "trust-evidence"))
