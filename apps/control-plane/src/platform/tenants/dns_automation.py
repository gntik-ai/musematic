from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.logging import get_logger
from platform.tenants.exceptions import DnsAutomationFailedError
from typing import Protocol

import httpx

LOGGER = get_logger(__name__)


class DnsAutomationClient(Protocol):
    async def ensure_records(self, subdomain: str) -> None: ...


class HetznerDnsAutomationClient:
    def __init__(
        self,
        *,
        settings: PlatformSettings,
        api_token: str,
        zone_id: str,
        ipv4_address: str,
        ipv6_address: str | None = None,
    ) -> None:
        self.settings = settings
        self.api_token = api_token
        self.zone_id = zone_id
        self.ipv4_address = ipv4_address
        self.ipv6_address = ipv6_address

    async def ensure_records(self, subdomain: str) -> None:
        headers = {"Auth-API-Token": self.api_token}
        records = [
            {"type": "A", "name": subdomain, "value": self.ipv4_address, "zone_id": self.zone_id}
        ]
        if self.ipv6_address:
            records.append(
                {
                    "type": "AAAA",
                    "name": subdomain,
                    "value": self.ipv6_address,
                    "zone_id": self.zone_id,
                }
            )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for record in records:
                    response = await client.post(
                        "https://dns.hetzner.com/api/v1/records",
                        headers=headers,
                        json=record,
                    )
                    response.raise_for_status()
        except Exception as exc:  # pragma: no cover - network dependent
            raise DnsAutomationFailedError(str(exc)) from exc


class MockDnsAutomationClient:
    def __init__(self) -> None:
        self.requests: list[str] = []

    async def ensure_records(self, subdomain: str) -> None:
        self.requests.append(subdomain)
        LOGGER.info("tenants.dns.mock_records_ready", tenant_subdomain=subdomain)


def build_dns_automation_client(settings: PlatformSettings) -> DnsAutomationClient:
    if settings.profile in {"production", "prod"}:
        token = getattr(settings, "HETZNER_DNS_API_TOKEN", "")
        zone_id = getattr(settings, "HETZNER_DNS_ZONE_ID", "")
        ipv4 = getattr(settings, "TENANT_DNS_IPV4_ADDRESS", "")
        ipv6 = getattr(settings, "TENANT_DNS_IPV6_ADDRESS", "")
        if token and zone_id and ipv4:
            return HetznerDnsAutomationClient(
                settings=settings,
                api_token=str(token),
                zone_id=str(zone_id),
                ipv4_address=str(ipv4),
                ipv6_address=str(ipv6) or None,
            )
    return MockDnsAutomationClient()
