"""Default-tenant onboarding wizard state for UPD-048 FR-024 through FR-031."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.accounts.events import (
    AccountsEventType,
    OnboardingDismissedPayload,
    OnboardingRelaunchedPayload,
    OnboardingStepAdvancedPayload,
    publish_accounts_event,
)
from platform.accounts.exceptions import DefaultWorkspaceNotProvisionedError
from platform.accounts.metrics import Counter
from platform.accounts.models import User, UserOnboardingState
from platform.accounts.schemas import (
    OnboardingStateView,
    OnboardingStepFirstAgent,
    OnboardingStepInvitations,
    OnboardingStepTour,
    OnboardingStepWorkspaceName,
)
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.tenant_context import current_tenant
from platform.workspaces.models import Workspace
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

accounts_onboarding_step_advanced_total = Counter(
    "accounts_onboarding_step_advanced_total",
    "Onboarding wizard step advances.",
    ["from_step", "to_step"],
)
accounts_onboarding_dismissed_total = Counter(
    "accounts_onboarding_dismissed_total",
    "Onboarding wizard dismissals.",
    ["at_step"],
)

STEP_SEQUENCE = ("workspace_named", "invitations", "first_agent", "tour", "done")


class OnboardingWizardService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: PlatformSettings,
        producer: EventProducer | None = None,
        audit_chain: AuditChainService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.producer = producer
        self.audit_chain = audit_chain

    async def get_or_create_state(self, user_id: UUID) -> OnboardingStateView:
        state = await self._state_for_user(user_id)
        if state is None:
            user = await self.session.get(User, user_id)
            tenant_id = self._tenant_id(user)
            state = UserOnboardingState(user_id=user_id, tenant_id=tenant_id)
            self.session.add(state)
            await self.session.flush()
        return await self._view(state)

    async def advance_step(
        self,
        user_id: UUID,
        step: str,
        payload: (
            OnboardingStepWorkspaceName
            | OnboardingStepInvitations
            | OnboardingStepFirstAgent
            | OnboardingStepTour
        ),
    ) -> dict[str, object]:
        state = await self._ensure_state(user_id)
        from_step = state.last_step_attempted
        if step == "workspace-name":
            await self._rename_default_workspace(user_id, payload)
            state.step_workspace_named = True
            to_step = "invitations"
        elif step == "invitations":
            state.step_invitations_sent_or_skipped = True
            first_agent_available = await self.is_first_agent_step_available()
            to_step = "first_agent" if first_agent_available else "tour"
        elif step == "first-agent":
            state.step_first_agent_created_or_skipped = True
            to_step = "tour"
        elif step == "tour":
            state.step_tour_started_or_skipped = True
            to_step = "done"
        else:
            raise ValueError(f"unknown onboarding step: {step}")

        state.last_step_attempted = to_step
        state.dismissed_at = None
        await self.session.flush()
        accounts_onboarding_step_advanced_total.labels(from_step, to_step).inc()
        await self._publish(
            AccountsEventType.onboarding_step_advanced,
            OnboardingStepAdvancedPayload(user_id=user_id, from_step=from_step, to_step=to_step),
            state.tenant_id,
        )
        await self._append_audit(
            "accounts.onboarding.step_advanced",
            state.tenant_id,
            {"user_id": str(user_id), "from_step": from_step, "to_step": to_step},
        )
        result: dict[str, object] = {"next_step": to_step}
        if step == "invitations" and isinstance(payload, OnboardingStepInvitations):
            result["invitations_sent"] = len(payload.invitations)
        return result

    async def dismiss(self, user_id: UUID) -> dict[str, datetime]:
        state = await self._ensure_state(user_id)
        state.dismissed_at = datetime.now(UTC)
        await self.session.flush()
        accounts_onboarding_dismissed_total.labels(state.last_step_attempted).inc()
        await self._publish(
            AccountsEventType.onboarding_dismissed,
            OnboardingDismissedPayload(
                user_id=user_id,
                dismissed_at_step=state.last_step_attempted,
            ),
            state.tenant_id,
        )
        await self._append_audit(
            "accounts.onboarding.dismissed",
            state.tenant_id,
            {"user_id": str(user_id), "dismissed_at_step": state.last_step_attempted},
        )
        return {"dismissed_at": state.dismissed_at}

    async def relaunch(self, user_id: UUID) -> OnboardingStateView:
        state = await self._ensure_state(user_id)
        from_step = state.last_step_attempted
        state.dismissed_at = None
        state.last_step_attempted = self._first_incomplete_step(state)
        await self.session.flush()
        await self._publish(
            AccountsEventType.onboarding_relaunched,
            OnboardingRelaunchedPayload(user_id=user_id, from_step=from_step),
            state.tenant_id,
        )
        await self._append_audit(
            "accounts.onboarding.relaunched",
            state.tenant_id,
            {"user_id": str(user_id), "from_step": from_step},
        )
        return await self._view(state)

    async def is_first_agent_step_available(self) -> bool:
        feature_flags = getattr(self.settings, "feature_flags", None)
        if isinstance(feature_flags, dict):
            return bool(feature_flags.get("FEATURE_FIRST_AGENT_ONBOARDING", True))
        return True

    async def _state_for_user(self, user_id: UUID) -> UserOnboardingState | None:
        result = await self.session.execute(
            select(UserOnboardingState).where(UserOnboardingState.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _ensure_state(self, user_id: UUID) -> UserOnboardingState:
        state = await self._state_for_user(user_id)
        if state is None:
            await self.get_or_create_state(user_id)
            state = await self._state_for_user(user_id)
        if state is None:  # pragma: no cover - guarded by flush above
            raise LookupError("onboarding state was not created")
        return state

    async def _view(self, state: UserOnboardingState) -> OnboardingStateView:
        workspace = await self._default_workspace(state.user_id)
        return OnboardingStateView(
            user_id=state.user_id,
            tenant_id=state.tenant_id,
            step_workspace_named=state.step_workspace_named,
            step_invitations_sent_or_skipped=state.step_invitations_sent_or_skipped,
            step_first_agent_created_or_skipped=state.step_first_agent_created_or_skipped,
            step_tour_started_or_skipped=state.step_tour_started_or_skipped,
            last_step_attempted=state.last_step_attempted,
            dismissed_at=state.dismissed_at,
            first_agent_step_available=await self.is_first_agent_step_available(),
            default_workspace_id=workspace.id if workspace else None,
            default_workspace_name=workspace.name if workspace else None,
        )

    async def _rename_default_workspace(
        self,
        user_id: UUID,
        payload: object,
    ) -> None:
        if not isinstance(payload, OnboardingStepWorkspaceName):
            return
        workspace = await self._default_workspace(user_id)
        if workspace is None:
            raise DefaultWorkspaceNotProvisionedError()
        workspace.name = payload.workspace_name
        await self.session.flush()

    async def _default_workspace(self, user_id: UUID) -> Workspace | None:
        result = await self.session.execute(
            select(Workspace).where(
                Workspace.owner_id == user_id,
                Workspace.is_default.is_(True),
            )
        )
        return result.scalar_one_or_none()

    def _tenant_id(self, user: User | None) -> UUID:
        tenant = current_tenant.get(None)
        if tenant is not None:
            return tenant.id
        if user is not None:
            return user.tenant_id
        raise LookupError("tenant context is required to create onboarding state")

    @staticmethod
    def _first_incomplete_step(state: UserOnboardingState) -> str:
        if not state.step_workspace_named:
            return "workspace_named"
        if not state.step_invitations_sent_or_skipped:
            return "invitations"
        if not state.step_first_agent_created_or_skipped:
            return "first_agent"
        if not state.step_tour_started_or_skipped:
            return "tour"
        return "done"

    async def _publish(
        self,
        event_type: AccountsEventType,
        payload: object,
        tenant_id: UUID,
    ) -> None:
        await publish_accounts_event(
            self.producer,
            event_type,
            payload,  # type: ignore[arg-type]
            CorrelationContext(correlation_id=uuid4(), tenant_id=tenant_id),
        )

    async def _append_audit(
        self,
        event_type: str,
        tenant_id: UUID,
        payload: dict[str, object],
    ) -> None:
        if self.audit_chain is None:
            return
        canonical_payload = {"tenant_id": str(tenant_id), **payload}
        canonical = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        await self.audit_chain.append(
            uuid4(),
            "accounts.onboarding",
            canonical,
            event_type=event_type,
            canonical_payload_json=canonical_payload,
            tenant_id=tenant_id,
        )
