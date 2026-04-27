from __future__ import annotations

from platform.localization.services.locale_resolver import LocaleResolver

import pytest


@pytest.mark.asyncio
async def test_locale_resolver_uses_url_before_preference_and_browser() -> None:
    resolver = LocaleResolver()

    locale, source = await resolver.resolve(
        url_hint="ja",
        user_preference="de",
        accept_language="fr-FR,fr;q=0.9,en;q=0.8",
    )

    assert locale == "ja"
    assert source == "url"


@pytest.mark.asyncio
async def test_locale_resolver_falls_back_through_unsupported_url_hint() -> None:
    resolver = LocaleResolver()

    locale, source = await resolver.resolve(
        url_hint="pt-BR",
        user_preference="es",
        accept_language="fr-FR,fr;q=0.9,en;q=0.8",
    )

    assert locale == "es"
    assert source == "preference"


@pytest.mark.asyncio
async def test_locale_resolver_matches_weighted_accept_language() -> None:
    resolver = LocaleResolver()

    locale, source = await resolver.resolve(
        url_hint=None,
        user_preference=None,
        accept_language="en-US;q=0.5,zh-CN;q=0.9,de-DE;q=0.7",
    )

    assert locale == "zh-CN"
    assert source == "browser"


@pytest.mark.asyncio
async def test_locale_resolver_defaults_when_no_supported_candidate() -> None:
    resolver = LocaleResolver()

    locale, source = await resolver.resolve(
        url_hint="pt-BR",
        user_preference=None,
        accept_language="it-IT,it;q=0.9",
    )

    assert locale == "en"
    assert source == "default"


def test_locale_resolver_matches_case_primary_and_accept_language_edges() -> None:
    resolver = LocaleResolver()

    assert resolver._match("   ") is None
    assert resolver._match("ZH_cn") == "zh-CN"
    assert resolver._match("fr-CA") == "fr"
    assert resolver._parse_accept_language(None) == []
    assert resolver._parse_accept_language(
        " , fr;level=regional;q=0.3, de;q=bad, *;q=1, en;q=0"
    ) == ["fr"]
