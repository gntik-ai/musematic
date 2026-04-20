"use client";

import { useState } from "react";
import { AlertTriangle, Coins, MessageSquareText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  formatUsdCost,
  humanizeMarketplaceValue,
  type AgentDetail as MarketplaceAgentDetail,
  type AgentReview,
} from "@/lib/types/marketplace";
import { TrustSignalsPanel } from "@/components/features/marketplace/trust-signals-panel";
import { PolicyList } from "@/components/features/marketplace/policy-list";
import { QualityMetrics } from "@/components/features/marketplace/quality-metrics";
import { AgentRevisions } from "@/components/features/marketplace/agent-revisions";
import { ReviewsSection } from "@/components/features/marketplace/reviews-section";
import { InvokeAgentDialog } from "@/components/features/marketplace/invoke-agent-dialog";
import { CreatorAnalyticsTab } from "@/components/features/marketplace/creator-analytics-tab";

type TabValue = "overview" | "policies" | "quality" | "reviews" | "analytics";

export interface AgentDetailProps {
  agent: MarketplaceAgentDetail;
  isOwner: boolean;
  currentUserReview?: AgentReview | null;
}

function certificationTone(status: MarketplaceAgentDetail["certificationStatus"]): string {
  switch (status) {
    case "active":
      return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300";
    case "expired":
      return "bg-red-500/15 text-red-700 dark:text-red-300";
    case "pending":
      return "bg-amber-500/15 text-amber-700 dark:text-amber-300";
    case "none":
      return "bg-slate-500/15 text-slate-700 dark:text-slate-300";
  }
}

function certificationLabel(status: MarketplaceAgentDetail["certificationStatus"]): string {
  switch (status) {
    case "active":
      return "Certified";
    case "expired":
      return "Certification expired";
    case "pending":
      return "Certification pending";
    case "none":
      return "Not certified";
  }
}

export function AgentDetail({
  agent,
  isOwner,
  currentUserReview = null,
}: AgentDetailProps) {
  const [activeTab, setActiveTab] = useState<TabValue>("overview");
  const canInvoke = agent.visibility.visibleToCurrentUser && agent.certificationStatus !== "expired";
  const activeCertification = agent.trustSignals.certificationBadges.find((badge) => badge.isActive) ?? agent.trustSignals.certificationBadges[0] ?? null;

  const tabs: Array<{ value: TabValue; label: string }> = [
    { value: "overview", label: "Overview" },
    { value: "policies", label: "Policies" },
    { value: "quality", label: "Quality Metrics" },
    { value: "reviews", label: "Reviews" },
  ];

  if (isOwner) {
    tabs.push({ value: "analytics", label: "Analytics" });
  }

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-4">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-accent">
                {agent.fqn}
              </p>
              <h1 className="text-4xl font-semibold tracking-tight">
                {agent.displayName}
              </h1>
              <p className="max-w-3xl text-base text-muted-foreground">
                {agent.fullDescription}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge
                aria-label={`Maturity: ${humanizeMarketplaceValue(agent.maturityLevel)}`}
                className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                variant="outline"
              >
                {humanizeMarketplaceValue(agent.maturityLevel)}
              </Badge>
              <Badge
                aria-label={`Trust tier: ${humanizeMarketplaceValue(agent.trustTier)}`}
                className="bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300"
                variant="outline"
              >
                {humanizeMarketplaceValue(agent.trustTier)}
              </Badge>
              <Badge className="border-border/60 bg-background/80 text-foreground" variant="outline">
                {agent.currentRevision}
              </Badge>
              <Badge className={certificationTone(agent.certificationStatus)} variant="outline">
                {certificationLabel(agent.certificationStatus)}
              </Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              {agent.capabilities.map((capability) => (
                <Badge
                  key={capability}
                  className="border-border/60 bg-background/80 text-foreground"
                  variant="outline"
                >
                  {humanizeMarketplaceValue(capability)}
                </Badge>
              ))}
            </div>
            {agent.certificationStatus !== "active" ? (
              <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-100">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4" />
                  <div>
                    <p className="font-medium">Agent not currently certified</p>
                    <p className="text-amber-900/80 dark:text-amber-100/80">
                      Invocation remains blocked until certification returns to an active state.
                    </p>
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          <div className="grid min-w-[280px] gap-3 rounded-3xl border border-border/60 bg-background/60 p-4">
            <div>
              <p className="text-sm text-muted-foreground">Cost tier</p>
              <p className="mt-1 font-semibold">
                {humanizeMarketplaceValue(agent.costBreakdown.tier)}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {formatUsdCost(agent.costBreakdown.estimatedCostPerInvocationUsd)} per invocation
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Certification</p>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <Badge className={certificationTone(agent.certificationStatus)} variant="outline">
                  {certificationLabel(agent.certificationStatus)}
                </Badge>
                <span className="text-sm font-medium text-foreground">
                  {activeCertification?.name ?? "Agent not currently certified"}
                </span>
              </div>
              {activeCertification ? (
                <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                  <p>Issued {new Date(activeCertification.issuedAt).toLocaleDateString()}</p>
                  <p>
                    Expires {activeCertification.expiresAt ? new Date(activeCertification.expiresAt).toLocaleDateString() : "No expiry"}
                  </p>
                </div>
              ) : null}
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Coins className="h-4 w-4" />
              Monthly cap {formatUsdCost(agent.costBreakdown.monthlyBudgetCapUsd)}
            </div>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <InvokeAgentDialog
                    agentDisplayName={agent.displayName}
                    agentFqn={agent.fqn}
                    isVisible={canInvoke}
                    trigger={
                      <Button className="w-full" disabled={!canInvoke}>
                        <MessageSquareText className="h-4 w-4" />
                        Start Conversation
                      </Button>
                    }
                  />
                </TooltipTrigger>
                {!canInvoke ? (
                  <TooltipContent>
                    Agent is not currently certified for use
                  </TooltipContent>
                ) : null}
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>
      </section>

      <Tabs>
        <TabsList className="flex w-full flex-wrap gap-2 rounded-2xl bg-muted/60 p-2">
          {tabs.map((tab) => {
            const active = activeTab === tab.value;

            return (
              <TabsTrigger
                key={tab.value}
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-background/70 hover:text-foreground"
                }
                onClick={() => setActiveTab(tab.value)}
              >
                {tab.label}
              </TabsTrigger>
            );
          })}
        </TabsList>

        {activeTab === "overview" ? (
          <TabsContent>
            <TrustSignalsPanel trustSignals={agent.trustSignals} />
          </TabsContent>
        ) : null}

        {activeTab === "policies" ? (
          <TabsContent>
            <PolicyList policies={agent.policies} />
          </TabsContent>
        ) : null}

        {activeTab === "quality" ? (
          <TabsContent className="space-y-6">
            <QualityMetrics metrics={agent.qualityMetrics} />
            <AgentRevisions
              currentVersion={agent.currentRevision}
              revisions={agent.revisions}
            />
          </TabsContent>
        ) : null}

        {activeTab === "reviews" ? (
          <TabsContent>
            <ReviewsSection
              agentFqn={agent.fqn}
              currentUserReview={currentUserReview}
            />
          </TabsContent>
        ) : null}

        {activeTab === "analytics" && isOwner ? (
          <TabsContent>
            <CreatorAnalyticsTab agentFqn={agent.fqn} />
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  );
}
