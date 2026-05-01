from __future__ import annotations

from platform.status_page.dependencies import (
    enforce_subscribe_rate_limit,
    get_status_page_repository,
    get_status_page_service,
)
from platform.status_page.exceptions import RateLimitExceededError
from platform.status_page.repository import StatusPageRepository
from platform.status_page.service import StatusPageService
from types import SimpleNamespace

import pytest


class _RedisCounter:
    def __init__(self, count: int) -> None:
        self.count = count
        self.expired: tuple[str, int] | None = None

    async def incr(self, key: str) -> int:
        self.key = key
        return self.count

    async def expire(self, key: str, seconds: int) -> None:
        self.expired = (key, seconds)


def _request(redis_client: object | None = None, *, host: str | None = "127.0.0.1"):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                clients={
                    "redis": redis_client,
                    "email_deliverer": object(),
                    "webhook_deliverer": object(),
                    "slack_deliverer": object(),
                },
                smtp_settings={"host": "smtp"},
                settings=SimpleNamespace(profile="test"),
            )
        ),
        client=SimpleNamespace(host=host) if host else None,
    )


@pytest.mark.asyncio
async def test_status_page_dependencies_build_services_and_rate_limit_paths() -> None:
    session = object()
    repository = get_status_page_repository(session)  # type: ignore[arg-type]
    assert isinstance(repository, StatusPageRepository)
    assert repository.session is session

    service = get_status_page_service(_request(), repository)
    assert isinstance(service, StatusPageService)
    assert service.repository is repository
    assert service.platform_version == "test"
    assert service.smtp_settings == {"host": "smtp"}

    await enforce_subscribe_rate_limit(_request(redis_client=None))
    await enforce_subscribe_rate_limit(_request(redis_client=object()))

    first = _RedisCounter(1)
    await enforce_subscribe_rate_limit(_request(redis_client=first))
    assert first.key == "status:subscribe:rate:127.0.0.1"
    assert first.expired == ("status:subscribe:rate:127.0.0.1", 60)

    allowed = _RedisCounter(10)
    await enforce_subscribe_rate_limit(_request(redis_client=allowed, host=None))
    assert allowed.key == "status:subscribe:rate:unknown"

    with pytest.raises(RateLimitExceededError):
        await enforce_subscribe_rate_limit(_request(redis_client=_RedisCounter(11)))
