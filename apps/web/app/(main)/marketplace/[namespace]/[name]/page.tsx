"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentDetail } from "@/components/features/marketplace/agent-detail";
import { useAgentDetail } from "@/lib/hooks/use-agent-detail";
import { useAuthStore } from "@/store/auth-store";
import { ApiError } from "@/types/api";

export default function AgentDetailPage() {
  const params = useParams<{ namespace: string; name: string }>();
  const namespace = decodeURIComponent(params.namespace);
  const name = decodeURIComponent(params.name);
  const userId = useAuthStore((state) => state.user?.id ?? null);
  const detailQuery = useAgentDetail(namespace, name);

  if (detailQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-48 rounded-3xl" />
        <Skeleton className="h-80 rounded-3xl" />
      </div>
    );
  }

  if (
    detailQuery.isError &&
    detailQuery.error instanceof ApiError &&
    detailQuery.error.status === 404
  ) {
    return (
      <EmptyState
        ctaLabel="Back to Marketplace"
        description="This agent is no longer available."
        icon={AlertTriangle}
        onCtaClick={() => {
          window.location.assign("/marketplace");
        }}
        title="Agent unavailable"
      />
    );
  }

  if (detailQuery.isError || !detailQuery.data) {
    return (
      <EmptyState
        ctaLabel="Back to Marketplace"
        description="The agent detail page could not be loaded right now."
        icon={AlertTriangle}
        onCtaClick={() => {
          window.location.assign("/marketplace");
        }}
        title="Unable to load agent"
      />
    );
  }

  return (
    <div className="space-y-4">
      <Link
        className="inline-flex text-sm font-medium text-brand-primary transition hover:text-brand-primary/80"
        href="/marketplace"
      >
        Back to Marketplace
      </Link>
      <AgentDetail
        agent={detailQuery.data}
        isOwner={detailQuery.data.createdById === userId}
      />
    </div>
  );
}
