from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ImpersonationContext:
    impersonation_session_id: UUID
    impersonation_user_id: UUID
    effective_user_id: UUID


_impersonation_context: ContextVar[ImpersonationContext | None] = ContextVar(
    "impersonation_context",
    default=None,
)


def set_impersonation_context(context: ImpersonationContext | None) -> None:
    _impersonation_context.set(context)


def get_impersonation_context() -> ImpersonationContext | None:
    return _impersonation_context.get()
