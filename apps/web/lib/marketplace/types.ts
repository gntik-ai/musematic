/**
 * UPD-049 — TypeScript mirrors of the new Pydantic schemas in
 * `apps/control-plane/src/platform/registry/schemas.py`. Kept hand-rolled
 * (rather than auto-generated from OpenAPI) to keep the change cost low
 * while the spec is iterating; once UPD-049 ships, the OpenAPI generator
 * (UPD-073 API governance) supersedes this file.
 *
 * Mirror fidelity: exhaustive — every field maps 1:1.
 */

import type { MarketingCategory } from "./categories";

export type MarketplaceScope = "workspace" | "tenant" | "public_default_tenant";

export type ReviewStatus =
  | "draft"
  | "pending_review"
  | "approved"
  | "rejected"
  | "published"
  | "deprecated";

/** Body of the public-publish marketing metadata sub-block. */
export interface MarketingMetadata {
  category: MarketingCategory;
  marketing_description: string;
  tags: string[];
}

/** Body of `POST /api/v1/registry/agents/{id}/publish` (extended). */
export interface PublishWithScopeRequest {
  scope: MarketplaceScope;
  marketing_metadata?: MarketingMetadata;
}

/** Body of `POST /api/v1/registry/agents/{id}/marketplace-scope`. */
export interface MarketplaceScopeChangeRequest {
  scope: MarketplaceScope;
}

/** Body of `POST /api/v1/registry/agents/{id}/deprecate-listing`. */
export interface DeprecateListingRequest {
  reason: string;
}

/** A row in the platform-staff review queue. */
export interface ReviewSubmissionView {
  agent_id: string;
  agent_fqn: string;
  tenant_slug: string;
  submitter_user_id: string;
  submitter_email: string;
  category: string;
  marketing_description: string;
  tags: string[];
  submitted_at: string;
  claimed_by_user_id: string | null;
  age_minutes: number;
}

export interface ReviewQueueResponse {
  items: ReviewSubmissionView[];
  next_cursor: string | null;
}

/** Body of the approve action — notes optional. */
export interface ReviewApprovalRequest {
  notes?: string | null;
}

/** Body of the reject action — reason required. */
export interface ReviewRejectionRequest {
  reason: string;
}

/** Body of `POST /api/v1/registry/agents/{source_id}/fork`. */
export interface ForkAgentRequest {
  target_scope: "workspace" | "tenant";
  target_workspace_id?: string;
  new_name: string;
}

export interface ForkAgentResponse {
  agent_id: string;
  fqn: string;
  marketplace_scope: MarketplaceScope;
  review_status: ReviewStatus;
  forked_from_agent_id: string;
  forked_from_fqn: string;
  tool_dependencies_missing: string[];
}
