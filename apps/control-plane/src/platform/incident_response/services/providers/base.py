from __future__ import annotations

import logging
from dataclasses import dataclass, field
from platform.common.clients.model_router import SecretProvider
from platform.incident_response.models import Incident, IncidentIntegration
from typing import Any, Protocol

import httpx

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProviderRef:
    provider_reference: str
    native_metadata: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable


class PagingProviderClient(Protocol):
    async def create_alert(
        self,
        *,
        integration: IncidentIntegration,
        incident: Incident,
        mapped_severity: str,
    ) -> ProviderRef: ...

    async def resolve_alert(
        self,
        *,
        integration: IncidentIntegration,
        provider_reference: str,
    ) -> None: ...


class BaseHttpPagingProvider:
    provider: str
    base_url: str

    def __init__(
        self,
        *,
        secret_provider: SecretProvider,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.secret_provider = secret_provider
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def _secret(self, integration: IncidentIntegration) -> str:
        return await self.secret_provider.get_current(integration.integration_key_ref)

    async def _post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any],
    ) -> dict[str, Any]:
        if not url.startswith("https://"):
            raise ProviderError(
                "Plain-text provider endpoint refused",
                provider=self.provider,
                retryable=False,
            )
        safe_headers = _redact_headers(headers or {})
        LOGGER.info(
            "incident_response_provider_request",
            extra={
                "provider": self.provider,
                "method": "POST",
                "url": url,
                "headers": safe_headers,
            },
        )
        try:
            response = await self.client.post(url, headers=headers, json=json)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "Provider request timed out",
                provider=self.provider,
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), provider=self.provider, retryable=True) from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"Provider returned HTTP {response.status_code}",
                provider=self.provider,
                status_code=response.status_code,
                retryable=response.status_code >= 500,
            )
        try:
            parsed = response.json()
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        name: ("<redacted>" if name.lower() == "authorization" else value)
        for name, value in headers.items()
    }
