"use client";

import { useRouter } from "next/navigation";
import { ArrowRight, GitCompareArrows, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { AgentIdentity, CertificationStatus } from "@/types/fqn";
import type { AgentCard as MarketplaceAgentCard } from "@/lib/types/marketplace";
import { buildAgentHref } from "@/lib/types/marketplace";

interface ReviewSummary {
  averageRating?: number | null;
  reviewCount?: number;
}

export interface AgentCardFqnProps {
  agent: AgentIdentity & { reviewSummary?: ReviewSummary; displayName?: string };
  href?: string;
  isSelected?: boolean;
  compareDisabled?: boolean;
  onInvoke?: () => void;
  onAddToCompare?: () => void;
}

function certificationTone(status: CertificationStatus["status"] | null): string {
  switch (status) {
    case "valid":
      return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300";
    case "expiring_soon":
      return "bg-amber-500/15 text-amber-700 dark:text-amber-300";
    case "expired":
    case "revoked":
      return "bg-red-500/15 text-red-700 dark:text-red-300";
    default:
      return "bg-slate-500/15 text-slate-700 dark:text-slate-300";
  }
}

function certificationLabel(certification: CertificationStatus | null): string {
  if (!certification) {
    return "Not certified";
  }
  switch (certification.status) {
    case "valid":
      return "Certified";
    case "expiring_soon":
      return `Expires in ${certification.daysUntilExpiry} days`;
    case "expired":
      return "Certification expired";
    case "revoked":
      return "Certification revoked";
  }
}

function canInvoke(certification: CertificationStatus | null): boolean {
  if (!certification) {
    return true;
  }
  return certification.status !== "expired" && certification.status !== "revoked";
}

function excerpt(text: string | null | undefined): string {
  const value = text?.trim() ?? "";
  if (!value) {
    return "No purpose summary available yet.";
  }
  return value.length > 120 ? `${value.slice(0, 117)}...` : value;
}

export function toAgentCardIdentity(agent: MarketplaceAgentCard) {
  const certification: CertificationStatus | null =
    agent.certificationStatus === "expired"
      ? {
          certifierId: `${agent.id}-certifier`,
          certifierName: "Certification authority",
          issuedAt: "",
          expiresAt: "",
          status: "expired",
          daysUntilExpiry: 0,
        }
      : agent.certificationStatus === "active"
        ? {
            certifierId: `${agent.id}-certifier`,
            certifierName: "Certification authority",
            issuedAt: "",
            expiresAt: "",
            status: "valid",
            daysUntilExpiry: 999,
          }
        : null;

  return {
    id: agent.id,
    displayName: agent.displayName,
    namespace: agent.namespace || null,
    localName: agent.localName || null,
    fqn: agent.fqn || null,
    purpose: agent.shortDescription,
    approach: null,
    roleType: null,
    visibilityPatterns: [],
    certification,
    reviewSummary: {
      averageRating: agent.averageRating,
      reviewCount: agent.reviewCount,
    },
  } satisfies AgentIdentity & { reviewSummary?: ReviewSummary; displayName?: string };
}

export function AgentCardFqn({
  agent,
  href,
  isSelected = false,
  compareDisabled = false,
  onInvoke,
  onAddToCompare,
}: AgentCardFqnProps) {
  const router = useRouter();
  const resolvedHref =
    href ??
    (agent.namespace && agent.localName
      ? buildAgentHref(agent.namespace, agent.localName)
      : undefined);

  const handleOpen = () => {
    if (resolvedHref) {
      router.push(resolvedHref);
    }
  };

  const invokeAllowed = canInvoke(agent.certification);

  return (
    <Card
      className="group flex h-full cursor-pointer flex-col overflow-hidden rounded-3xl border-border/60 bg-card/80 transition hover:-translate-y-0.5 hover:border-brand-accent/40 hover:shadow-lg"
      role={resolvedHref ? "link" : undefined}
      tabIndex={resolvedHref ? 0 : undefined}
      onClick={resolvedHref ? handleOpen : undefined}
      onKeyDown={
        resolvedHref
          ? (event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                handleOpen();
              }
            }
          : undefined
      }
    >
      <CardHeader className="space-y-3 p-6">
        <div className="flex flex-wrap items-center gap-2">
          {agent.fqn ? (
            <Badge className="border-border/60 bg-background/80 text-foreground" variant="outline">
              {agent.fqn}
            </Badge>
          ) : (
            <Badge className="border-transparent bg-slate-500/15 text-slate-700 dark:text-slate-300" variant="outline">
              Legacy agent
            </Badge>
          )}
          <Badge className={cn("border-transparent", certificationTone(agent.certification?.status ?? null))} variant="outline">
            <ShieldCheck className="mr-1 h-3 w-3" />
            {certificationLabel(agent.certification)}
          </Badge>
          {agent.roleType ? (
            <Badge className="border-border/60 bg-background/80 text-foreground" variant="outline">
              {String(agent.roleType).replace(/[_-]/g, " ")}
            </Badge>
          ) : null}
        </div>

        <div className="space-y-2">
          <CardTitle className="text-xl">
            {agent.displayName ?? agent.localName ?? agent.fqn ?? "Unnamed agent"}
          </CardTitle>
          <p className="text-sm text-muted-foreground">{excerpt(agent.purpose)}</p>
          {agent.reviewSummary?.reviewCount ? (
            <p className="text-xs text-muted-foreground">
              {agent.reviewSummary.averageRating?.toFixed(1) ?? "-"} / 5 from {agent.reviewSummary.reviewCount} reviews
            </p>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="flex-1">
        <p className="text-sm text-muted-foreground">
          {agent.approach?.trim() || "Identity, purpose, and certification status are available at a glance from the updated marketplace card."}
        </p>
      </CardContent>

      <CardFooter className="justify-between gap-3">
        {onAddToCompare ? (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <Button
                  disabled={compareDisabled}
                  size="sm"
                  type="button"
                  variant={isSelected ? "default" : "outline"}
                  onClick={(event) => {
                    event.stopPropagation();
                    onAddToCompare();
                  }}
                >
                  <GitCompareArrows className="h-4 w-4" />
                  {isSelected ? "Selected" : "Compare"}
                </Button>
              </TooltipTrigger>
              {compareDisabled ? (
                <TooltipContent>Maximum compare selection reached</TooltipContent>
              ) : null}
            </Tooltip>
          </TooltipProvider>
        ) : <span />}

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger>
              <Button
                disabled={!invokeAllowed}
                size="sm"
                type="button"
                variant="ghost"
                onClick={(event) => {
                  event.stopPropagation();
                  if (invokeAllowed) {
                    if (onInvoke) {
                      onInvoke();
                    } else {
                      handleOpen();
                    }
                  }
                }}
              >
                {invokeAllowed ? "Invoke" : "Unavailable"}
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </Button>
            </TooltipTrigger>
            {!invokeAllowed ? (
              <TooltipContent>Agent is not currently certified for use</TooltipContent>
            ) : null}
          </Tooltip>
        </TooltipProvider>
      </CardFooter>
    </Card>
  );
}
