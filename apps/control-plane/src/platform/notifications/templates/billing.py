from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class BillingOverageRequiredAlert:
    workspace_id: UUID
    quota_name: str
    current: int | float | str | None
    limit: int | float | str | None

    @property
    def deep_link(self) -> str:
        return f"/workspaces/{self.workspace_id}/billing/overage-authorize"

    @property
    def title(self) -> str:
        return "Overage authorization required"

    @property
    def body(self) -> str:
        return (
            f"The workspace reached {self.quota_name}. "
            f"Current usage is {self.current} against a limit of {self.limit}."
        )
