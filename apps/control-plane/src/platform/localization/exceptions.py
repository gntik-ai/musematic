from __future__ import annotations

from platform.common.exceptions import NotFoundError, PlatformError, ValidationError
from uuid import UUID


class UnsupportedLocaleError(ValidationError):
    def __init__(self, locale_code: str) -> None:
        super().__init__(
            "UNSUPPORTED_LOCALE",
            "Locale is not supported.",
            {"locale_code": locale_code},
        )


class InvalidThemeError(ValidationError):
    def __init__(self, theme: str) -> None:
        super().__init__("INVALID_THEME", "Theme is not supported.", {"theme": theme})


class InvalidTimezoneError(ValidationError):
    def __init__(self, timezone: str) -> None:
        super().__init__(
            "INVALID_TIMEZONE",
            "Timezone must be a valid IANA timezone.",
            {"timezone": timezone},
        )


class LocaleFileNotFoundError(NotFoundError):
    def __init__(self, locale_code: str) -> None:
        super().__init__(
            "LOCALE_FILE_NOT_FOUND",
            "Locale file not found.",
            {"locale_code": locale_code},
        )


class LocaleFileVersionConflictError(PlatformError):
    status_code = 409

    def __init__(self, locale_code: str) -> None:
        super().__init__(
            "LOCALE_FILE_VERSION_CONFLICT",
            "Another locale publish is already in progress.",
            {"locale_code": locale_code},
        )


class WorkspaceNotMemberError(ValidationError):
    def __init__(self, workspace_id: UUID) -> None:
        super().__init__(
            "WORKSPACE_NOT_MEMBER",
            "Default workspace must be a workspace the user can access.",
            {"workspace_id": str(workspace_id)},
        )


class DataExportFormatInvalidError(ValidationError):
    def __init__(self, data_export_format: str) -> None:
        super().__init__(
            "DATA_EXPORT_FORMAT_INVALID",
            "Data export format is not supported.",
            {"data_export_format": data_export_format},
        )

