from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

import httpx

ProviderName = Literal["pagerduty", "opsgenie", "victorops"]


@dataclass(slots=True)
class ProviderMock:
    """In-process httpx mock for paging-provider smoke tests."""

    provider: ProviderName
    status_code: int = 202
    requests: list[dict[str, Any]] = field(default_factory=list)

    @property
    def base_url(self) -> str:
        match self.provider:
            case "pagerduty":
                return "https://events.pagerduty.com"
            case "opsgenie":
                return "https://api.opsgenie.com"
            case "victorops":
                return "https://alert.victorops.com"

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, transport=self.transport())

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        payload = _json(request)
        self.requests.append(
            {
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "json": payload,
            }
        )
        error_status = _forced_status(request, payload)
        if error_status is not None:
            return _error_response(self.provider, error_status)
        if self.status_code >= 400:
            return _error_response(self.provider, self.status_code)
        return httpx.Response(
            self.status_code,
            json=_success_payload(self.provider, payload),
            request=request,
        )


def provider_mock(provider: ProviderName, *, status_code: int = 202) -> ProviderMock:
    return ProviderMock(provider=provider, status_code=status_code)


def _json(request: httpx.Request) -> dict[str, Any]:
    try:
        payload = json.loads(request.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _forced_status(request: httpx.Request, payload: dict[str, Any]) -> int | None:
    header = request.headers.get("x-musematic-mock-status")
    if header:
        return int(header)
    status = payload.get("mock_status")
    return int(status) if isinstance(status, int) else None


def _success_payload(provider: ProviderName, payload: dict[str, Any]) -> dict[str, Any]:
    match provider:
        case "pagerduty":
            return {
                "status": "success",
                "message": "Event processed",
                "dedup_key": str(payload.get("dedup_key") or uuid4()),
            }
        case "opsgenie":
            return {
                "result": "Request will be processed",
                "requestId": str(payload.get("alias") or uuid4()),
                "took": 0.001,
            }
        case "victorops":
            return {
                "result": "success",
                "entity_id": str(payload.get("entity_id") or uuid4()),
            }


def _error_response(provider: ProviderName, status_code: int) -> httpx.Response:
    body = {
        "provider": provider,
        "status": "error",
        "message": f"mock {provider} returned HTTP {status_code}",
        "retryable": status_code >= 500,
    }
    return httpx.Response(status_code, json=body)
