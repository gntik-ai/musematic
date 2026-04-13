"use client";

import { useRouter } from "next/navigation";
import { ArrowRight, GitCompareArrows, ShieldCheck, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useComparisonStore } from "@/lib/stores/use-comparison-store";
import {
  formatUsdCost,
  humanizeMarketplaceValue,
  type AgentCard as MarketplaceAgentCard,
  type MaturityLevel,
  type TrustTier,
} from "@/lib/types/marketplace";
import { StarRating } from "@/components/features/marketplace/star-rating";
import { cn } from "@/lib/utils";

export interface AgentCardProps {
  agent: MarketplaceAgentCard;
  isSelected: boolean;
  onToggleCompare: (fqn: string) => void;
  href: string;
  compact?: boolean;
}

const maturityClasses: Record<MaturityLevel, string> = {
  draft: "bg-slate-500/15 text-slate-700 dark:text-slate-200",
  beta: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  production: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  deprecated: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
};

const trustClasses: Record<TrustTier, string> = {
  unverified: "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300",
  basic: "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300",
  standard: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-300",
  certified: "bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300",
};

export function AgentCard({
  agent,
  isSelected,
  onToggleCompare,
  href,
  compact = false,
}: AgentCardProps) {
  const router = useRouter();
  const canAdd = useComparisonStore((state) => state.selectedFqns.length < 4);
  const compareDisabled = !isSelected && !canAdd;

  const navigate = () => {
    router.push(href);
  };

  return (
    <Card
      aria-label={`View ${agent.displayName}`}
      className={cn(
        "group flex h-full cursor-pointer flex-col overflow-hidden rounded-3xl border-border/60 bg-card/80 transition hover:-translate-y-0.5 hover:border-brand-accent/40 hover:shadow-lg",
        compact ? "min-w-[280px]" : "",
      )}
      role="link"
      tabIndex={0}
      onClick={navigate}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          navigate();
        }
      }}
    >
      <CardHeader className={cn("space-y-3", compact ? "p-5" : "p-6")}>
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            aria-label={`Maturity: ${humanizeMarketplaceValue(agent.maturityLevel)}`}
            className={cn("border-transparent", maturityClasses[agent.maturityLevel])}
            variant="outline"
          >
            <Sparkles className="mr-1 h-3 w-3" />
            {humanizeMarketplaceValue(agent.maturityLevel)}
          </Badge>
          <Badge
            aria-label={`Trust tier: ${humanizeMarketplaceValue(agent.trustTier)}`}
            className={cn("border-transparent", trustClasses[agent.trustTier])}
            variant="outline"
          >
            <ShieldCheck className="mr-1 h-3 w-3" />
            {humanizeMarketplaceValue(agent.trustTier)}
          </Badge>
          <Badge className="border-border/60 bg-background/80 text-foreground" variant="outline">
            {humanizeMarketplaceValue(agent.costTier)}
          </Badge>
        </div>

        <div className="space-y-2">
          <div className="space-y-1">
            <p className="text-xs uppercase tracking-[0.18em] text-brand-accent">
              {agent.namespace}
            </p>
            <CardTitle className={cn(compact ? "text-lg" : "text-xl")}>
              {agent.displayName}
            </CardTitle>
          </div>
          <p className="text-sm text-muted-foreground">
            {agent.shortDescription}
          </p>
        </div>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-4">
        <StarRating
          rating={agent.averageRating}
          reviewCount={agent.reviewCount}
          size={compact ? "sm" : "md"}
        />
        <div className="flex flex-wrap gap-2">
          {agent.capabilities.slice(0, compact ? 2 : 3).map((capability) => (
            <Badge
              key={capability}
              className="border-border/60 bg-background/80 text-foreground"
              variant="outline"
            >
              {humanizeMarketplaceValue(capability)}
            </Badge>
          ))}
          {agent.capabilities.length > (compact ? 2 : 3) ? (
            <Badge className="border-border/60 bg-background/80 text-foreground" variant="outline">
              +{agent.capabilities.length - (compact ? 2 : 3)} more
            </Badge>
          ) : null}
        </div>
        <div className="grid grid-cols-2 gap-3 rounded-2xl bg-muted/40 p-3 text-sm">
          <div>
            <p className="text-xs uppercase tracking-[0.12em] text-muted-foreground">
              Revision
            </p>
            <p className="mt-1 font-medium">{agent.currentRevision}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.12em] text-muted-foreground">
              Est. cost
            </p>
            <p className="mt-1 font-medium">
              {formatUsdCost(
                agent.costTier === "free"
                  ? 0
                  : agent.costTier === "low"
                    ? 0.03
                    : agent.costTier === "medium"
                      ? 0.12
                      : 0.45,
              )}
            </p>
          </div>
        </div>
      </CardContent>

      <CardFooter className="justify-between gap-3">
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
                  onToggleCompare(agent.fqn);
                }}
              >
                <GitCompareArrows className="h-4 w-4" />
                {isSelected ? "Selected" : "Compare"}
              </Button>
            </TooltipTrigger>
            {compareDisabled ? (
              <TooltipContent>
                Maximum of 4 agents can be compared at once
              </TooltipContent>
            ) : null}
          </Tooltip>
        </TooltipProvider>

        <Button
          size="sm"
          variant="ghost"
          onClick={(event) => {
            event.stopPropagation();
            navigate();
          }}
        >
          Details
          <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
        </Button>
      </CardFooter>
    </Card>
  );
}
