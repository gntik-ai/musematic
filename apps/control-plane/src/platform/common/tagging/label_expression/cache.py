from __future__ import annotations

import json
from collections import OrderedDict
from platform.common.tagging.constants import REDIS_KEY_AST_TEMPLATE, REDIS_KEY_AST_TTL_SECONDS
from platform.common.tagging.label_expression.ast import ASTNode, node_from_dict
from platform.common.tagging.label_expression.parser import parse
from typing import Any
from uuid import UUID


class LabelExpressionCache:
    def __init__(
        self,
        redis_client: Any | None = None,
        *,
        lru_size: int = 256,
        ttl_seconds: int = REDIS_KEY_AST_TTL_SECONDS,
    ) -> None:
        self.redis_client = redis_client
        self.lru_size = max(lru_size, 0)
        self.ttl_seconds = ttl_seconds
        self._lru: OrderedDict[tuple[str, int], ASTNode] = OrderedDict()

    async def get_or_compile(
        self,
        policy_id: UUID | str,
        version: int,
        expression: str | None,
    ) -> ASTNode | None:
        if expression is None:
            return None
        lru_key = (str(policy_id), int(version))
        cached = self._lru_get(lru_key)
        if cached is not None:
            return cached

        redis_key = REDIS_KEY_AST_TEMPLATE.format(policy_id=policy_id, version=version)
        redis_payload = await self._redis_get(redis_key)
        if redis_payload is not None:
            node = node_from_dict(dict(redis_payload["ast"]))
            self._lru_set(lru_key, node)
            return node

        node = parse(expression)
        await self._redis_set(redis_key, {"ast": node.to_dict()})
        self._lru_set(lru_key, node)
        return node

    async def invalidate(self, policy_id: UUID | str, version: int) -> None:
        lru_key = (str(policy_id), int(version))
        self._lru.pop(lru_key, None)
        if self.redis_client is not None:
            await self.redis_client.delete(
                REDIS_KEY_AST_TEMPLATE.format(policy_id=policy_id, version=version)
            )

    def _lru_get(self, key: tuple[str, int]) -> ASTNode | None:
        node = self._lru.get(key)
        if node is None:
            return None
        self._lru.move_to_end(key)
        return node

    def _lru_set(self, key: tuple[str, int], node: ASTNode) -> None:
        if self.lru_size <= 0:
            return
        self._lru[key] = node
        self._lru.move_to_end(key)
        while len(self._lru) > self.lru_size:
            self._lru.popitem(last=False)

    async def _redis_get(self, key: str) -> dict[str, Any] | None:
        if self.redis_client is None:
            return None
        raw = await self.redis_client.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            decoded = raw.decode("utf-8")
        else:
            decoded = str(raw)
        payload = json.loads(decoded)
        return dict(payload) if isinstance(payload, dict) else None

    async def _redis_set(self, key: str, payload: dict[str, Any]) -> None:
        if self.redis_client is None:
            return
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        await self.redis_client.set(key, encoded, ttl=self.ttl_seconds)
