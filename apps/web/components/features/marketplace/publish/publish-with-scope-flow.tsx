"use client";

/**
 * UPD-049 — Scope-aware publish flow component.
 *
 * Wraps `ScopePickerStep` + `MarketingMetadataForm` and the
 * `usePublishWithScope` mutation into one self-contained surface that
 * any agent-management page can drop in. Surfaces 429 rate-limit
 * refusals with a humanised "try again in N minutes" message.
 *
 * Drop-in usage:
 *
 *   <PublishWithScopeFlow
 *     agentId={agent.id}
 *     tenantKind={tenantContext.kind}
 *     onPublished={() => router.refresh()}
 *   />
 *
 * The component handles its own state — pickers, validation, submit.
 * The parent only supplies the agent's id, the tenant kind from the
 * resolved tenant context, and an `onPublished` callback for cache
 * invalidation / navigation.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/lib/hooks/use-toast";
import { ApiError } from "@/types/api";
import { usePublishWithScope } from "@/lib/hooks/use-publish-with-scope";
import {
  MarketingMetadataForm,
  isMarketingMetadataValid,
} from "@/components/features/marketplace/publish/marketing-metadata-form";
import { ScopePickerStep } from "@/components/features/marketplace/publish/scope-picker-step";
import type {
  MarketingMetadata,
  MarketplaceScope,
} from "@/lib/marketplace/types";

const EMPTY_METADATA: MarketingMetadata = {
  category: "other",
  marketing_description: "",
  tags: [],
};

export interface PublishWithScopeFlowProps {
  agentId: string;
  tenantKind: "default" | "enterprise";
  onPublished?: () => void;
}

function humaniseRetryAfter(seconds: number): string {
  if (seconds < 60) return `${seconds} seconds`;
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  const hours = Math.ceil(minutes / 60);
  return `${hours} hour${hours === 1 ? "" : "s"}`;
}

export function PublishWithScopeFlow({
  agentId,
  tenantKind,
  onPublished,
}: PublishWithScopeFlowProps) {
  const [scope, setScope] = useState<MarketplaceScope>("workspace");
  const [metadata, setMetadata] = useState<MarketingMetadata>(EMPTY_METADATA);
  const [showErrors, setShowErrors] = useState(false);
  const publish = usePublishWithScope();
  const { toast } = useToast();

  const isPublic = scope === "public_default_tenant";
  const canSubmit =
    !publish.isPending && (!isPublic || isMarketingMetadataValid(metadata));

  const submit = async () => {
    if (isPublic && !isMarketingMetadataValid(metadata)) {
      setShowErrors(true);
      return;
    }
    try {
      await publish.mutateAsync({
        agentId,
        body: isPublic
          ? { scope, marketing_metadata: metadata }
          : { scope },
      });
      toast({
        title:
          scope === "public_default_tenant"
            ? "Submitted for review"
            : "Agent published",
        description:
          scope === "public_default_tenant"
            ? "Your submission is now in the platform-staff review queue."
            : undefined,
        variant: "success",
      });
      onPublished?.();
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        // Backend includes retry_after_seconds in meta (the catch-all
        // dictionary on PlatformError); fall back to 60 seconds if absent.
        const retryRaw = error.meta?.["retry_after_seconds"];
        const retry =
          typeof retryRaw === "number" && Number.isFinite(retryRaw)
            ? retryRaw
            : 60;
        toast({
          title: "Submission rate limit reached",
          description: `You can submit again in ${humaniseRetryAfter(retry)}.`,
          variant: "destructive",
        });
        return;
      }
      toast({
        title: error instanceof ApiError ? error.message : "Publish failed",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-base font-semibold">Choose where this agent appears</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Workspace and tenant scopes publish immediately. Public submissions
          go to the platform-staff review queue.
        </p>
        <ScopePickerStep
          className="mt-3"
          value={scope}
          onChange={setScope}
          tenantKind={tenantKind}
        />
      </section>

      {isPublic ? (
        <section className="space-y-3">
          <h3 className="text-base font-semibold">Marketing details</h3>
          <p className="text-sm text-muted-foreground">
            These fields appear on the public marketplace listing card and
            help reviewers and users decide whether the agent fits their needs.
          </p>
          <MarketingMetadataForm
            value={metadata}
            onChange={setMetadata}
            showErrors={showErrors}
          />
        </section>
      ) : null}

      <div className="flex justify-end">
        <Button onClick={() => void submit()} disabled={!canSubmit}>
          {publish.isPending
            ? "Submitting…"
            : isPublic
            ? "Submit for review"
            : "Publish"}
        </Button>
      </div>
    </div>
  );
}
