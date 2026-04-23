"use client";

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { wsClient } from "@/lib/ws";
import { useVerdictFeed } from "@/lib/hooks/use-verdict-feed";
import type { GovernanceVerdict } from "@/types/governance";
import { cn } from "@/lib/utils";

interface VerdictFeedItem extends GovernanceVerdict {
  isAnimated?: boolean;
  isSuperseded?: boolean;
}

export interface VerdictFeedProps {
  workspaceId: string | null;
}

export function VerdictFeed({ workspaceId }: VerdictFeedProps) {
  const { items } = useVerdictFeed();
  const [liveItems, setLiveItems] = useState<VerdictFeedItem[]>(items);

  useEffect(() => {
    setLiveItems(items);
  }, [items]);

  useEffect(() => {
    wsClient.connect();
    const unsubscribe = wsClient.subscribe<Record<string, unknown>>("governance-verdicts", (event) => {
      const payload = event.payload;
      const workspaceMatch = workspaceId ? String(payload.workspaceId ?? payload.workspace_id ?? "") === workspaceId : true;
      if (!workspaceMatch) {
        return;
      }
      if (event.type === "verdict.issued") {
        const nextItem: VerdictFeedItem = {
          id: String(payload.id ?? crypto.randomUUID()),
          offendingAgentFqn: String(payload.offendingAgentFqn ?? payload.target_agent_fqn ?? "unknown:agent"),
          verdictType: String(payload.verdictType ?? payload.verdict_type ?? "policy_violation") as GovernanceVerdict["verdictType"],
          enforcerAgentFqn: String(payload.enforcerAgentFqn ?? payload.judge_agent_fqn ?? "governance:judge"),
          actionTaken: String(payload.actionTaken ?? payload.recommended_action ?? "warn") as GovernanceVerdict["actionTaken"],
          issuedAt: String(payload.issuedAt ?? payload.created_at ?? new Date().toISOString()),
          rationaleExcerpt: String(payload.rationaleExcerpt ?? payload.rationale ?? ""),
          isAnimated: true,
        };
        setLiveItems((current) => [nextItem, ...current]);
        window.setTimeout(() => {
          setLiveItems((current) => current.map((item) => item.id === nextItem.id ? { ...item, isAnimated: false } : item));
        }, 500);
      }
      if (event.type === "verdict.superseded") {
        const verdictId = String(payload.id ?? payload.verdictId ?? "");
        setLiveItems((current) => current.map((item) => item.id === verdictId ? { ...item, isSuperseded: true } : item));
      }
    });
    return () => unsubscribe();
  }, [workspaceId]);

  const renderedItems = useMemo(() => liveItems.slice(0, 20), [liveItems]);

  return (
    <div aria-live="polite" className="space-y-3">
      {renderedItems.map((item) => (
        <article
          key={item.id}
          className={cn(
            "rounded-2xl border border-border/70 bg-card/80 p-4 transition-colors",
            item.isAnimated && "animate-pulse",
            item.isSuperseded && "opacity-60 line-through",
          )}
        >
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{item.offendingAgentFqn}</p>
            <Badge variant="secondary">{item.verdictType}</Badge>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {item.enforcerAgentFqn} · {item.actionTaken}
          </p>
        </article>
      ))}
    </div>
  );
}
