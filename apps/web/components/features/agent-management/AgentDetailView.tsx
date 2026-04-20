"use client";

import { useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AgentProfileA2aTab } from "@/components/features/agents/agent-profile-a2a-tab";
import { AgentProfileContractsTab } from "@/components/features/agents/agent-profile-contracts-tab";
import { AgentProfileMcpTab } from "@/components/features/agents/agent-profile-mcp-tab";
import { AgentMetadataEditor } from "@/components/features/agent-management/AgentMetadataEditor";
import { AgentPublicationPanel } from "@/components/features/agent-management/AgentPublicationPanel";
import { AgentHealthScoreGauge } from "@/components/features/agent-management/AgentHealthScoreGauge";
import { AgentMaturityBadge } from "@/components/features/agent-management/AgentMaturityBadge";
import { AgentStatusBadge } from "@/components/features/agent-management/AgentStatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { AgentDetail } from "@/lib/types/agent-management";

type AgentDetailTab =
  | "overview"
  | "metadata"
  | "policies"
  | "certifications"
  | "evaluations"
  | "revisions"
  | "contracts"
  | "a2a"
  | "mcp";

const DETAIL_TABS: AgentDetailTab[] = [
  "overview",
  "metadata",
  "policies",
  "certifications",
  "evaluations",
  "revisions",
  "contracts",
  "a2a",
  "mcp",
];

function resolveTab(value: string | null): AgentDetailTab {
  if (value && DETAIL_TABS.includes(value as AgentDetailTab)) {
    return value as AgentDetailTab;
  }
  return "overview";
}

export interface AgentDetailViewProps {
  agent: AgentDetail;
}

export function AgentDetailView({ agent }: AgentDetailViewProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab = useMemo(() => resolveTab(searchParams.get("tab")), [searchParams]);

  const setActiveTab = (tab: AgentDetailTab) => {
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set("tab", tab);
    router.replace(`${pathname}?${nextParams.toString()}`);
  };

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-4">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-accent">{agent.fqn}</p>
              <h1 className="text-4xl font-semibold tracking-tight">{agent.name}</h1>
              <p className="max-w-3xl text-base text-muted-foreground">{agent.description}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <AgentMaturityBadge maturity={agent.maturity_level} />
              <AgentStatusBadge status={agent.status} />
            </div>
            <div className="grid gap-3 text-sm text-muted-foreground md:grid-cols-2">
              <p><span className="font-medium text-foreground">Namespace:</span> {agent.namespace}</p>
              <p><span className="font-medium text-foreground">Category:</span> {agent.category}</p>
              <p><span className="font-medium text-foreground">Revision:</span> {agent.latest_revision_number}</p>
              <p><span className="font-medium text-foreground">Updated:</span> {new Date(agent.updated_at).toLocaleString()}</p>
            </div>
          </div>
          <div className="min-w-[280px] rounded-3xl border border-border/60 bg-background/60 p-5">
            <AgentHealthScoreGauge fqn={agent.fqn} size="lg" />
          </div>
        </div>
      </section>

      <Tabs>
        <TabsList className="flex w-full flex-wrap gap-2 rounded-2xl bg-muted/60 p-2">
          {DETAIL_TABS.map((tab) => {
            const active = activeTab === tab;
            return (
              <TabsTrigger
                key={tab}
                aria-current={active ? "page" : undefined}
                className={active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:bg-background/70 hover:text-foreground"}
                onClick={() => setActiveTab(tab)}
              >
                {tab.replace("_", " ")}
              </TabsTrigger>
            );
          })}
        </TabsList>

        {activeTab === "overview" ? (
          <TabsContent className="grid gap-4 lg:grid-cols-[1.15fr,0.85fr]">
            <Card>
              <CardHeader>
                <CardTitle>Operational summary</CardTitle>
                <CardDescription>Core metadata and purpose at a glance.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <div>
                  <p className="font-medium text-foreground">Purpose</p>
                  <p className="text-muted-foreground">{agent.purpose}</p>
                </div>
                <div>
                  <p className="font-medium text-foreground">Approach</p>
                  <p className="text-muted-foreground">{agent.approach ?? "No approach documented."}</p>
                </div>
                <div>
                  <p className="font-medium text-foreground">Tags</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {agent.tags.map((tag) => (
                      <span key={tag} className="rounded-full border border-border/60 bg-background px-3 py-1 text-xs text-foreground">{tag}</span>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Lifecycle context</CardTitle>
                <CardDescription>Current visibility and reasoning profile.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <p><span className="font-medium text-foreground">Role type:</span> {agent.role_type}</p>
                <p><span className="font-medium text-foreground">Reasoning modes:</span> {agent.reasoning_modes.join(", ")}</p>
                <p><span className="font-medium text-foreground">Visibility patterns:</span> {agent.visibility_patterns.length}</p>
              </CardContent>
            </Card>
          </TabsContent>
        ) : activeTab === "metadata" ? (
          <TabsContent>
            <AgentMetadataEditor fqn={agent.fqn} />
          </TabsContent>
        ) : activeTab === "revisions" ? (
          <TabsContent>
            <div className="flex justify-start">
              <button className="rounded-md border border-border px-4 py-2 text-sm" type="button" onClick={() => router.push(`/agent-management/${encodeURIComponent(agent.fqn)}/revisions`)}>
                Open revision timeline
              </button>
            </div>
          </TabsContent>
        ) : activeTab === "evaluations" ? (
          <TabsContent>
            <AgentPublicationPanel currentStatus={agent.status} fqn={agent.fqn} onPublished={() => router.refresh()} />
          </TabsContent>
        ) : activeTab === "contracts" ? (
          <TabsContent>
            <AgentProfileContractsTab agentId={agent.fqn} />
          </TabsContent>
        ) : activeTab === "a2a" ? (
          <TabsContent>
            <AgentProfileA2aTab agentId={agent.fqn} />
          </TabsContent>
        ) : activeTab === "mcp" ? (
          <TabsContent>
            <AgentProfileMcpTab agentId={agent.fqn} />
          </TabsContent>
        ) : (
          <TabsContent>
            <EmptyState description={`The ${activeTab} workspace is wired and ready for its dedicated implementation phase.`} title={`${activeTab.charAt(0).toUpperCase()}${activeTab.slice(1)} coming next`} />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
