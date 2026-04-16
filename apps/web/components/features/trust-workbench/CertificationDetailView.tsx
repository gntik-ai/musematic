"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { format } from "date-fns";
import { ShieldCheck, ShieldPlus, ShieldQuestion, ShieldX } from "lucide-react";
import { StatusTimeline } from "@/components/features/trust-workbench/StatusTimeline";
import { EvidenceList } from "@/components/features/trust-workbench/EvidenceList";
import { ReviewerForm } from "@/components/features/trust-workbench/ReviewerForm";
import { TrustRadarChart } from "@/components/features/trust-workbench/TrustRadarChart";
import { PolicyAttachmentPanel } from "@/components/features/trust-workbench/PolicyAttachmentPanel";
import { PrivacyImpactPanel } from "@/components/features/trust-workbench/PrivacyImpactPanel";
import { CertificationStatusBadge } from "@/components/features/trust-workbench/CertificationStatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTrustRadar } from "@/lib/hooks/use-trust-radar";
import {
  isTrustWorkbenchDetailTab,
  type CertificationDetail,
  type TrustWorkbenchDetailTab,
} from "@/lib/types/trust-workbench";

export interface CertificationDetailViewProps {
  certification: CertificationDetail;
  workspaceId: string;
  tabsConfig?: TrustWorkbenchDetailTab[];
}

const defaultTabs: { id: TrustWorkbenchDetailTab; label: string }[] = [
  { id: "evidence", label: "Evidence" },
  { id: "trust-radar", label: "Trust radar" },
  { id: "policies", label: "Policies" },
  { id: "privacy", label: "Privacy" },
];

export function CertificationDetailView({
  certification,
  workspaceId,
  tabsConfig,
}: CertificationDetailViewProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab = isTrustWorkbenchDetailTab(searchParams.get("tab"))
    ? (searchParams.get("tab") as TrustWorkbenchDetailTab)
    : "evidence";
  const tabs = defaultTabs.filter((tab) => !tabsConfig || tabsConfig.includes(tab.id));
  const trustRadarQuery = useTrustRadar(
    activeTab === "trust-radar" ? certification.agentId : null,
  );

  const updateTab = (tab: TrustWorkbenchDetailTab) => {
    const next = new URLSearchParams(searchParams.toString());
    if (tab === "evidence") {
      next.delete("tab");
    } else {
      next.set("tab", tab);
    }

    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  };

  const statusIcon = (() => {
    if (certification.status === "active") {
      return <ShieldCheck className="h-5 w-5 text-emerald-500" />;
    }
    if (certification.status === "revoked") {
      return <ShieldX className="h-5 w-5 text-destructive" />;
    }
    if (certification.status === "pending") {
      return <ShieldQuestion className="h-5 w-5 text-amber-500" />;
    }

    return <ShieldPlus className="h-5 w-5 text-muted-foreground" />;
  })();

  return (
    <div className="space-y-6">
      <header className="overflow-hidden rounded-[2rem] border bg-[radial-gradient(circle_at_top_left,hsl(var(--brand-accent)/0.18),transparent_24%),linear-gradient(140deg,hsl(var(--card))_0%,hsl(var(--muted)/0.52)_100%)] p-6 shadow-sm">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              {statusIcon}
              <CertificationStatusBadge
                expiresAt={certification.expiresAt}
                status={certification.status}
              />
            </div>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
                {certification.entityName}
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">
                {certification.entityFqn}
              </p>
            </div>
          </div>

          <div className="rounded-[1.75rem] border border-border/60 bg-background/75 p-4 shadow-sm">
            <p className="text-sm font-medium">{certification.certificationType}</p>
            <p className="mt-2 text-xs text-muted-foreground">
              Issued by {certification.issuedBy}
            </p>
            <p className="text-xs text-muted-foreground">
              Created {format(new Date(certification.createdAt), "PPp")}
            </p>
            <p className="text-xs text-muted-foreground">
              {certification.expiresAt
                ? `Expires ${format(new Date(certification.expiresAt), "PPp")}`
                : "No expiry"}
            </p>
          </div>
        </div>
      </header>

      <section className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 shadow-sm">
        <div className="mb-4">
          <h2 className="text-xl font-semibold">Status history</h2>
        </div>
        <StatusTimeline
          currentStatus={certification.status}
          events={certification.statusHistory}
        />
      </section>

      <Tabs>
        <TabsList className="flex w-full flex-wrap gap-2 rounded-[1.5rem] bg-muted/60 p-2">
          {tabs.map((tab) => (
            <TabsTrigger
              key={tab.id}
              aria-pressed={activeTab === tab.id}
              className={activeTab === tab.id ? "bg-background shadow-sm" : undefined}
              onClick={() => updateTab(tab.id)}
            >
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {activeTab === "evidence" ? (
          <TabsContent className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
            <section className="space-y-4">
              <div>
                <h3 className="text-xl font-semibold">Evidence</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  Review collected evidence before recording the final decision.
                </p>
              </div>
              <EvidenceList items={certification.evidenceItems} />
            </section>
            <ReviewerForm
              agentId={certification.agentId}
              certificationId={certification.id}
              currentStatus={certification.status}
              isExpired={certification.status === "expired"}
              onDecisionSubmitted={() => {
                router.refresh();
              }}
            />
          </TabsContent>
        ) : null}

        {activeTab === "trust-radar" ? (
          <TabsContent>
            {trustRadarQuery.isLoading ? (
              <Skeleton className="min-h-[360px] rounded-[1.75rem]" />
            ) : trustRadarQuery.isError || !trustRadarQuery.data ? (
              <EmptyState
                description="Trust profile data is not available for this certification."
                title="Trust profile not available"
              />
            ) : (
              <TrustRadarChart profile={trustRadarQuery.data} />
            )}
          </TabsContent>
        ) : null}

        {activeTab === "policies" ? (
          <TabsContent>
            <PolicyAttachmentPanel
              agentId={certification.agentId}
              agentRevisionId={certification.agentRevisionId}
              workspaceId={workspaceId}
            />
          </TabsContent>
        ) : null}

        {activeTab === "privacy" ? (
          <TabsContent>
            <PrivacyImpactPanel agentId={certification.agentId} />
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  );
}
