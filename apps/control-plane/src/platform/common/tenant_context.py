from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID


class TenantContextNotSetError(RuntimeError):
    """Raised when tenant-scoped code runs outside a resolved request context."""


@dataclass(frozen=True, slots=True)
class TenantContext:
    id: UUID
    slug: str
    subdomain: str
    kind: Literal["default", "enterprise"]
    status: Literal["active", "suspended", "pending_deletion"]
    region: str
    branding: Mapping[str, Any] = field(default_factory=dict)
    feature_flags: Mapping[str, Any] = field(default_factory=dict)
    # UPD-049: explicit denormalized field for the consume_public_marketplace
    # flag. Reading via .feature_flags.get(...) also works, but the explicit
    # field keeps the RLS GUC-bind path on the hot DB connection-checkout
    # cheap and unambiguous (no key-miss → False fallback ambiguity).
    consume_public_marketplace: bool = False


current_tenant: ContextVar[TenantContext | None] = ContextVar(
    "current_tenant",
    default=None,
)


def get_current_tenant() -> TenantContext:
    tenant = current_tenant.get(None)
    if tenant is None:
        raise TenantContextNotSetError("Tenant context has not been set for this request.")
    return tenant


def set_current_tenant(tenant: TenantContext | None) -> Token[TenantContext | None]:
    return current_tenant.set(tenant)
