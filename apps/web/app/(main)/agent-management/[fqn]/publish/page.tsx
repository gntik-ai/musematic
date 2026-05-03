"use client";

/**
 * UPD-049 — Agent publish page (refresh-pass T026 wiring).
 *
 * Mounts the existing `PublishWithScopeFlow` component with the agent's
 * id and the caller's tenant kind. The flow handles scope picking,
 * marketing-metadata validation when scope is `public_default_tenant`,
 * and 429 rate-limit refusals.
 *
 * Tenant kind is sourced from the user's current membership (UPD-046)
 * via `useMemberships`. Enterprise tenants see the public option as
 * disabled with an explanation; the backend refuses public-scope
 * publish from non-default tenants regardless (FR-741).
 */

import { use, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PublishWithScopeFlow } from "@/components/features/marketplace/publish/publish-with-scope-flow";
import { useAgent } from "@/lib/hooks/use-agents";
import { useMemberships } from "@/lib/hooks/use-memberships";
import { useWorkspaceStore } from "@/store/workspace-store";
import { ApiError } from "@/types/api";

export default function AgentPublishPage({
  params,
}: {
  params: Promise<{ fqn: string }>;
}) {
  const router = useRouter();
  const resolvedParams = use(params);
  const workspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const fqn = useMemo(
    () => decodeURIComponent(resolvedParams.fqn),
    [resolvedParams.fqn],
  );
  const agentQuery = useAgent(fqn, { workspaceId });
  const memberships = useMemberships();
  const tenantKind = memberships.currentMembership?.tenant_kind ?? "default";

  useEffect(() => {
    if (
      agentQuery.error instanceof ApiError &&
      agentQuery.error.status === 404
    ) {
      router.replace("/agent-management");
    }
  }, [agentQuery.error, router]);

  if (agentQuery.isLoading || memberships.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!agentQuery.data) {
    return (
      <EmptyState
        title="Agent not found"
        description="The agent you are trying to publish does not exist or you do not have access."
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-mono">
          Publish {agentQuery.data.fqn}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <PublishWithScopeFlow
          agentId={agentQuery.data.id}
          tenantKind={tenantKind}
          onPublished={() => router.push(`/agent-management/${resolvedParams.fqn}`)}
        />
      </CardContent>
    </Card>
  );
}
