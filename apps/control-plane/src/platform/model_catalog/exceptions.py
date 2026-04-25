from __future__ import annotations

from platform.common.exceptions import PlatformError, ValidationError


class ModelCatalogError(PlatformError):
    status_code = 500
    error_code = "model_catalog_error"


class ModelCatalogValidationError(ValidationError):
    error_code = "model_catalog_validation_error"


class ModelCatalogNotFoundError(ModelCatalogError):
    status_code = 404
    error_code = "model_catalog_not_found"


class ModelBindingError(ModelCatalogValidationError):
    error_code = "model_binding_invalid"


class InvalidBindingError(ModelBindingError):
    error_code = "model_binding_missing"


class CatalogEntryNotFoundError(ModelCatalogError):
    status_code = 502
    error_code = "model_catalog_entry_not_found"


class ModelBlockedError(ModelCatalogError):
    status_code = 503
    error_code = "model_blocked"


class CredentialNotConfiguredError(ModelCatalogError):
    status_code = 503
    error_code = "model_provider_credential_missing"


class FallbackExhaustedError(ModelCatalogError):
    status_code = 502
    error_code = "model_fallback_exhausted"


class PromptInjectionBlocked(ModelCatalogValidationError):  # noqa: N818
    error_code = "prompt_injection_blocked"


class ProviderCallError(ModelCatalogError):
    status_code = 502
    error_code = "provider_call_failed"
