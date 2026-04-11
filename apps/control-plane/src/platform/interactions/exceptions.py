from __future__ import annotations

from platform.common.exceptions import NotFoundError, PlatformError, ValidationError
from uuid import UUID


class InteractionError(PlatformError):
    """Base interactions bounded-context error."""


class InvalidStateTransitionError(InteractionError):
    status_code = 409

    def __init__(self, current_state: str, trigger: str) -> None:
        super().__init__(
            "INTERACTION_INVALID_STATE_TRANSITION",
            f"Cannot apply trigger '{trigger}' from state '{current_state}'",
            details={"current_state": current_state, "trigger": trigger},
        )
        self.current_state = current_state
        self.trigger = trigger


class ConversationNotFoundError(NotFoundError):
    def __init__(self, conversation_id: UUID) -> None:
        super().__init__(
            "CONVERSATION_NOT_FOUND",
            f"Conversation '{conversation_id}' was not found",
        )


class InteractionNotFoundError(NotFoundError):
    def __init__(self, interaction_id: UUID) -> None:
        super().__init__(
            "INTERACTION_NOT_FOUND",
            f"Interaction '{interaction_id}' was not found",
        )


class MessageNotInInteractionError(ValidationError):
    def __init__(self, message_id: UUID, interaction_id: UUID) -> None:
        super().__init__(
            "MESSAGE_NOT_IN_INTERACTION",
            f"Message '{message_id}' does not belong to interaction '{interaction_id}'",
        )


class MessageLimitReachedError(InteractionError):
    status_code = 429

    def __init__(self, limit: int) -> None:
        super().__init__(
            "CONVERSATION_MESSAGE_LIMIT_REACHED",
            f"Conversation has reached the configured message limit ({limit})",
            details={"limit": limit},
        )


class InteractionNotAcceptingMessagesError(InteractionError):
    status_code = 409

    def __init__(self, interaction_id: UUID, state: str) -> None:
        super().__init__(
            "INTERACTION_NOT_ACCEPTING_MESSAGES",
            f"Interaction '{interaction_id}' is not accepting messages in state '{state}'",
            details={"interaction_id": str(interaction_id), "state": state},
        )


class GoalNotAcceptingMessagesError(InteractionError):
    status_code = 409

    def __init__(self, goal_id: UUID, status: str) -> None:
        super().__init__(
            "GOAL_NOT_ACCEPTING_MESSAGES",
            f"Goal '{goal_id}' is not accepting messages in status '{status}'",
            details={"goal_id": str(goal_id), "status": status},
        )


class BranchNotFoundError(NotFoundError):
    def __init__(self, branch_id: UUID) -> None:
        super().__init__(
            "BRANCH_NOT_FOUND",
            f"Branch '{branch_id}' was not found",
        )


class AttentionRequestNotFoundError(NotFoundError):
    def __init__(self, request_id: UUID) -> None:
        super().__init__(
            "ATTENTION_REQUEST_NOT_FOUND",
            f"Attention request '{request_id}' was not found",
        )
