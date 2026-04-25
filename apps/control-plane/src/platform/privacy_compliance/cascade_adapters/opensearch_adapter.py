from __future__ import annotations

from datetime import UTC, datetime
from platform.privacy_compliance.cascade_adapters.base import (
    CascadeAdapter,
    CascadePlan,
    CascadeResult,
)
from typing import Any
from uuid import UUID

OpenSearchDeleteResponse = dict[str, Any] | int


class OpenSearchCascadeAdapter(CascadeAdapter):
    store_name = "opensearch"

    def __init__(self, client: object | None, index: str = "*") -> None:
        self.client = client
        self.index = index

    async def dry_run(self, subject_user_id: UUID) -> CascadePlan:
        del subject_user_id
        return CascadePlan(self.store_name, 0, {self.index: 0})

    async def execute(self, subject_user_id: UUID) -> CascadeResult:
        started = datetime.now(UTC)
        errors: list[str] = []
        count = 0
        payload = {"query": {"term": {"user_id": str(subject_user_id)}}}
        try:
            response = await self._delete_by_query(payload)
            count = int(response.get("deleted", 0)) if isinstance(response, dict) else int(response)
        except Exception as exc:
            if not self._is_missing_index(exc):
                errors.append(str(exc))
        return CascadeResult(
            self.store_name,
            started,
            datetime.now(UTC),
            count,
            {self.index: count},
            errors,
        )

    async def _delete_by_query(self, payload: dict[str, Any]) -> dict[str, Any] | int:
        raw_client_factory = getattr(self.client, "_ensure_client", None)
        if callable(raw_client_factory):
            raw_client = await raw_client_factory()
            response = await raw_client.delete_by_query(
                index=self.index,
                body=payload,
                conflicts="proceed",
                ignore_unavailable=True,
            )
            return _delete_response(response)

        delete_by_query = getattr(self.client, "delete_by_query", None)
        if not callable(delete_by_query):
            return 0

        try:
            response = await delete_by_query(index=self.index, body=payload)
        except TypeError as exc:
            if "body" not in str(exc):
                raise
            response = await delete_by_query(
                index=self.index,
                query=payload["query"],
                workspace_id="",
            )
        return _delete_response(response)

    @staticmethod
    def _is_missing_index(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        message = str(exc).lower()
        return status == 404 or "index_not_found" in message or "no such index" in message


def _delete_response(response: object) -> OpenSearchDeleteResponse:
    if isinstance(response, int):
        return response
    if isinstance(response, dict):
        return response
    return 0
