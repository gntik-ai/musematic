from __future__ import annotations

from platform.common.exceptions import PlatformError
from uuid import UUID


class RegistryError(PlatformError):
    status_code = 400


class FQNConflictError(RegistryError):
    status_code = 409

    def __init__(self, fqn: str) -> None:
        super().__init__(
            "REGISTRY_FQN_CONFLICT",
            "Agent FQN already exists",
            {"fqn": fqn},
        )


class NamespaceConflictError(RegistryError):
    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(
            "REGISTRY_NAMESPACE_CONFLICT",
            "Namespace name already exists in this workspace",
            {"name": name},
        )


class NamespaceNotFoundError(RegistryError):
    status_code = 404

    def __init__(self, identifier: UUID | str) -> None:
        super().__init__(
            "REGISTRY_NAMESPACE_NOT_FOUND",
            "Registry namespace not found",
            {"namespace": str(identifier)},
        )


class PackageValidationError(RegistryError):
    status_code = 422

    def __init__(self, error_type: str, detail: str, field: str | None = None) -> None:
        details = {"error_type": error_type, "field": field}
        super().__init__("REGISTRY_PACKAGE_INVALID", detail, details)
        self.error_type = error_type
        self.field = field


class InvalidTransitionError(RegistryError):
    status_code = 409

    def __init__(self, current: str, target: str, valid: list[str]) -> None:
        super().__init__(
            "REGISTRY_INVALID_TRANSITION",
            (
                f"Invalid transition: {current} -> {target}. "
                f"Valid transitions from {current}: {valid}"
            ),
            {"current_status": current, "target_status": target, "valid_transitions": valid},
        )


class AgentNotFoundError(RegistryError):
    status_code = 404

    def __init__(self, identifier: UUID | str) -> None:
        super().__init__(
            "REGISTRY_AGENT_NOT_FOUND",
            "Registry agent not found",
            {"agent": str(identifier)},
        )


class WorkspaceAuthorizationError(RegistryError):
    status_code = 403

    def __init__(self, workspace_id: UUID) -> None:
        super().__init__(
            "REGISTRY_WORKSPACE_ACCESS_DENIED",
            "Requester does not have access to the workspace",
            {"workspace_id": str(workspace_id)},
        )


class RegistryStoreUnavailableError(RegistryError):
    status_code = 503

    def __init__(self, store: str, detail: str | None = None) -> None:
        super().__init__(
            "REGISTRY_STORE_UNAVAILABLE",
            detail or f"Registry dependency unavailable: {store}",
            {"store": store},
        )


class InvalidVisibilityPatternError(RegistryError):
    status_code = 422

    def __init__(self, pattern: str) -> None:
        super().__init__(
            "REGISTRY_INVALID_VISIBILITY_PATTERN",
            "Invalid visibility pattern",
            {"pattern": pattern},
        )


class RevisionConflictError(RegistryError):
    status_code = 409

    def __init__(self, version: str) -> None:
        super().__init__(
            "REGISTRY_REVISION_CONFLICT",
            "Agent revision already exists",
            {"version": version},
        )


class DecommissionImmutableError(RegistryError):
    status_code = 409

    def __init__(self, field_names: list[str]) -> None:
        super().__init__(
            "REGISTRY_DECOMMISSION_IMMUTABLE",
            "Decommission metadata is immutable once set",
            {"fields": field_names},
        )


# --- UPD-049 marketplace scope + public-review exceptions ------------------
# See specs/099-marketplace-scope/contracts/.


class PublicScopeNotAllowedForEnterpriseError(RegistryError):
    """Raised when a non-default tenant attempts public-marketplace publish.

    The application-service leg of the three-layer Enterprise refusal
    (UI scope-picker disable + service guard + DB CHECK constraint).
    """

    status_code = 403

    def __init__(self, tenant_slug: str) -> None:
        super().__init__(
            "REGISTRY_PUBLIC_SCOPE_NOT_ALLOWED_FOR_ENTERPRISE",
            "Public marketplace publishing is reserved to the default tenant",
            {"tenant_slug": tenant_slug},
        )


class MarketingMetadataRequiredError(RegistryError):
    status_code = 422

    def __init__(self) -> None:
        super().__init__(
            "REGISTRY_MARKETING_METADATA_REQUIRED",
            "marketing_metadata is required when publishing with public scope",
            {},
        )


class MarketingCategoryInvalidError(RegistryError):
    status_code = 422

    def __init__(self, category: str, allowed: tuple[str, ...]) -> None:
        super().__init__(
            "REGISTRY_MARKETING_CATEGORY_INVALID",
            "Marketing category is not in the platform-curated list",
            {"category": category, "allowed": list(allowed)},
        )


class SubmissionRateLimitExceededError(RegistryError):
    """Raised when a submitter exceeds 5 public-scope submissions in 24h.

    The router translates this into HTTP 429 with a `Retry-After` header.
    """

    status_code = 429

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "REGISTRY_SUBMISSION_RATE_LIMIT_EXCEEDED",
            "Public-marketplace submission rate limit exceeded",
            {"retry_after_seconds": retry_after_seconds},
        )
        self.retry_after_seconds = retry_after_seconds


class ReviewAlreadyClaimedError(RegistryError):
    status_code = 409

    def __init__(self, agent_id: UUID, claimed_by: UUID) -> None:
        super().__init__(
            "REGISTRY_REVIEW_ALREADY_CLAIMED",
            "This submission is already claimed by a different reviewer",
            {"agent_id": str(agent_id), "claimed_by": str(claimed_by)},
        )


# --- UPD-049 refresh (102) — self-review prevention + assignment ---------
# See specs/102-marketplace-scope/contracts/self-review-prevention.md and
# contracts/reviewer-assignment-rest.md.


class SelfReviewNotAllowedError(RegistryError):
    """Raised when a reviewer attempts to act on a submission they authored.

    Covers the four review-action verbs: ``assign``, ``claim``, ``approve``,
    ``reject``. The audit chain emits a
    ``marketplace.review.self_review_attempted`` entry separately; this
    exception only carries the API-layer error shape.
    """

    status_code = 403

    def __init__(
        self,
        *,
        submitter_user_id: UUID,
        actor_user_id: UUID,
        action: str,
    ) -> None:
        super().__init__(
            "REGISTRY_SELF_REVIEW_NOT_ALLOWED",
            "Reviewers cannot act on submissions they authored.",
            {
                "submitter_user_id": str(submitter_user_id),
                "actor_user_id": str(actor_user_id),
                "action": action,
            },
        )


class ReviewerAssignmentConflictError(RegistryError):
    """Raised when an assignment conflicts with an existing assignment.

    Two cases:
    * ``assign`` called with a different reviewer when the row is already
      assigned to someone else (caller must ``unassign`` first).
    * ``claim`` called by a reviewer who is not the currently-assigned
      reviewer (claim-jumping prevention).
    """

    status_code = 409

    def __init__(
        self,
        agent_id: UUID,
        assigned_reviewer_user_id: UUID,
    ) -> None:
        super().__init__(
            "REGISTRY_REVIEWER_ASSIGNMENT_CONFLICT",
            "This submission is assigned to a different reviewer.",
            {
                "agent_id": str(agent_id),
                "assigned_reviewer_user_id": str(assigned_reviewer_user_id),
            },
        )


class SubmissionNotInPendingReviewError(RegistryError):
    """Raised when assign/unassign is called on a submission outside ``pending_review``."""

    status_code = 409

    def __init__(self, agent_id: UUID, current_status: str) -> None:
        super().__init__(
            "REGISTRY_SUBMISSION_NOT_IN_PENDING_REVIEW",
            "Assignment is only valid while a submission is in pending_review.",
            {"agent_id": str(agent_id), "current_status": current_status},
        )


class SubmissionAlreadyResolvedError(RegistryError):
    status_code = 409

    def __init__(self, agent_id: UUID, current_status: str) -> None:
        super().__init__(
            "REGISTRY_SUBMISSION_ALREADY_RESOLVED",
            "This submission has already been approved or rejected",
            {"agent_id": str(agent_id), "current_status": current_status},
        )


class SubmissionNotFoundError(RegistryError):
    status_code = 404

    def __init__(self, agent_id: UUID) -> None:
        super().__init__(
            "REGISTRY_SUBMISSION_NOT_FOUND",
            "Marketplace submission not found",
            {"agent_id": str(agent_id)},
        )


class NotAgentOwnerError(RegistryError):
    status_code = 403

    def __init__(self, agent_id: UUID) -> None:
        super().__init__(
            "REGISTRY_NOT_AGENT_OWNER",
            "Caller is not the owner of this agent",
            {"agent_id": str(agent_id)},
        )


class SourceAgentNotVisibleError(RegistryError):
    """Raised when a fork target is not readable under the consumer's RLS.

    Distinct from `AgentNotFoundError` because the row may exist but be
    invisible cross-tenant; the API surfaces it as 404 to avoid leaking
    existence.
    """

    status_code = 404

    def __init__(self, source_id: UUID) -> None:
        super().__init__(
            "REGISTRY_SOURCE_AGENT_NOT_VISIBLE",
            "Source agent is not visible to the requester",
            {"source_id": str(source_id)},
        )


class ConsumePublicMarketplaceDisabledError(RegistryError):
    """Raised when an Enterprise tenant tries to fork a public agent without
    the `consume_public_marketplace` feature flag enabled."""

    status_code = 403

    def __init__(self, tenant_slug: str) -> None:
        super().__init__(
            "REGISTRY_CONSUME_PUBLIC_MARKETPLACE_DISABLED",
            "Public-marketplace consumption is disabled for this tenant",
            {"tenant_slug": tenant_slug},
        )


class NameTakenInTargetNamespaceError(RegistryError):
    status_code = 409

    def __init__(self, fqn: str) -> None:
        super().__init__(
            "REGISTRY_NAME_TAKEN_IN_TARGET_NAMESPACE",
            "Chosen name is already taken in the target namespace",
            {"fqn": fqn},
        )
