from __future__ import annotations

from platform.localization.services.locale_resolver import LocaleResolver

import httpx
import pytest

from .support import build_app

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_locale_resolver_endpoint_uses_url_preference_browser_default_order() -> None:
    app = build_app(
        current_user={"sub": "00000000-0000-0000-0000-000000000001"},
        locale_resolver=LocaleResolver(),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        url_wins = await client.post(
            "/api/v1/locales/resolve",
            json={
                "url_hint": "fr",
                "user_preference": "es",
                "accept_language": "de-DE,de;q=0.9",
            },
        )
        preference_wins = await client.post(
            "/api/v1/locales/resolve",
            json={
                "url_hint": "pt-BR",
                "user_preference": "es",
                "accept_language": "de-DE,de;q=0.9",
            },
        )
        browser_wins = await client.post(
            "/api/v1/locales/resolve",
            json={"accept_language": "ja-JP,ja;q=0.9"},
        )
        default_wins = await client.post(
            "/api/v1/locales/resolve",
            json={"accept_language": "pt-BR,pt;q=0.9"},
        )

    assert url_wins.json() == {"locale": "fr", "source": "url"}
    assert preference_wins.json() == {"locale": "es", "source": "preference"}
    assert browser_wins.json() == {"locale": "ja", "source": "browser"}
    assert default_wins.json() == {"locale": "en", "source": "default"}
