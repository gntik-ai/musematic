from __future__ import annotations

from platform.common.clients.model_provider_http import RateLimitedError


class RateLimitError(RateLimitedError):
    """Synthetic LLM provider HTTP 429 used by E2E-only mock provider injection."""
