"use client";

import Link from "next/link";
import { use } from "react";
import { SearchCheck } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { SessionTabs } from "@/components/features/discovery/SessionTabs";

interface DiscoveryEvidenceIndexPageProps {
  params: Promise<{ session_id: string }>;
}

export default function DiscoveryEvidenceIndexPage({
  params,
}: DiscoveryEvidenceIndexPageProps) {
  const { session_id } = use(params);

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Evidence</h1>
        <SessionTabs active="evidence" sessionId={session_id} />
      </div>
      <EmptyState
        description="Open a hypothesis to inspect its critique evidence and source links."
        icon={SearchCheck}
        title="Choose a hypothesis"
      />
      <Button asChild variant="outline">
        <Link href={`/discovery/${encodeURIComponent(session_id)}/hypotheses`}>
          Browse Hypotheses
        </Link>
      </Button>
    </section>
  );
}
