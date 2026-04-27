from __future__ import annotations

from platform.localization.constants import DEFAULT_LOCALE, LOCALES
from platform.localization.schemas import LocaleResolveSource


class LocaleResolver:
    def __init__(self, supported_locales: tuple[str, ...] = LOCALES) -> None:
        self.supported_locales = supported_locales

    async def resolve(
        self,
        *,
        url_hint: str | None,
        user_preference: str | None,
        accept_language: str | None,
    ) -> tuple[str, LocaleResolveSource]:
        for raw_value, source in (
            (url_hint, "url"),
            (user_preference, "preference"),
        ):
            matched = self._match(raw_value)
            if matched is not None:
                return matched, source  # type: ignore[return-value]

        for candidate in self._parse_accept_language(accept_language):
            matched = self._match(candidate)
            if matched is not None:
                return matched, "browser"

        return DEFAULT_LOCALE, "default"

    def _match(self, raw_value: str | None) -> str | None:
        if raw_value is None:
            return None
        normalized = raw_value.strip().replace("_", "-")
        if not normalized:
            return None
        if normalized in self.supported_locales:
            return normalized
        lower_supported = {item.lower(): item for item in self.supported_locales}
        if normalized.lower() in lower_supported:
            return lower_supported[normalized.lower()]
        primary = normalized.split("-", 1)[0].lower()
        for locale in self.supported_locales:
            if locale.lower().split("-", 1)[0] == primary:
                return locale
        return None

    @staticmethod
    def _parse_accept_language(value: str | None) -> list[str]:
        if not value:
            return []
        parsed: list[tuple[float, int, str]] = []
        for index, part in enumerate(value.split(",")):
            sections = [section.strip() for section in part.split(";") if section.strip()]
            if not sections:
                continue
            quality = 1.0
            for section in sections[1:]:
                if not section.startswith("q="):
                    continue
                try:
                    quality = float(section.removeprefix("q="))
                except ValueError:
                    quality = 0.0
            parsed.append((quality, index, sections[0]))
        parsed.sort(key=lambda item: (-item[0], item[1]))
        return [locale for quality, _index, locale in parsed if quality > 0 and locale != "*"]

