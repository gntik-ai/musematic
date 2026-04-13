"use client";

import { format } from "date-fns";
import { ShieldCheck, Award, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { humanizeMarketplaceValue, type TrustSignals } from "@/lib/types/marketplace";

const trustTierClasses = {
  unverified: "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300",
  basic: "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300",
  standard: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-300",
  certified: "bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300",
} as const;

export interface TrustSignalsPanelProps {
  trustSignals: TrustSignals;
}

export function TrustSignalsPanel({ trustSignals }: TrustSignalsPanelProps) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-5 w-5 text-brand-accent" />
            Trust posture
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <Badge
              aria-label={`Trust tier: ${humanizeMarketplaceValue(trustSignals.tier)}`}
              className={trustTierClasses[trustSignals.tier]}
              variant="outline"
            >
              {humanizeMarketplaceValue(trustSignals.tier)}
            </Badge>
            {trustSignals.latestEvaluation ? (
              <div className="text-sm text-muted-foreground">
                Latest score {(trustSignals.latestEvaluation.aggregateScore * 100).toFixed(0)}%
              </div>
            ) : null}
          </div>

          <div className="space-y-3">
            <h3 className="text-sm font-semibold">Certification badges</h3>
            {trustSignals.certificationBadges.length > 0 ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {trustSignals.certificationBadges.map((badge) => (
                  <div
                    key={badge.id}
                    className="rounded-2xl border border-border/60 bg-muted/30 p-4"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium">{badge.name}</p>
                      {badge.isActive ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-500 dark:text-emerald-300" />
                      ) : null}
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Issued {format(new Date(badge.issuedAt), "MMM d, yyyy")}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {badge.expiresAt
                        ? `Expires ${format(new Date(badge.expiresAt), "MMM d, yyyy")}`
                        : "No expiry"}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No active certifications published for this agent.
              </p>
            )}
          </div>

          {trustSignals.latestEvaluation ? (
            <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Award className="h-4 w-4 text-brand-accent" />
                Latest evaluation
              </div>
              <p className="mt-2 text-2xl font-semibold">
                {(trustSignals.latestEvaluation.aggregateScore * 100).toFixed(0)}%
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {trustSignals.latestEvaluation.passedCases}/
                {trustSignals.latestEvaluation.totalCases} cases passed on{" "}
                {format(
                  new Date(trustSignals.latestEvaluation.evaluatedAt),
                  "MMM d, yyyy",
                )}
              </p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tier progression</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-4">
            {trustSignals.tierHistory.map((entry) => (
              <li key={`${entry.tier}-${entry.achievedAt}`} className="relative pl-6">
                <span className="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full bg-brand-accent" />
                <p className="font-medium">{humanizeMarketplaceValue(entry.tier)}</p>
                <p className="text-sm text-muted-foreground">
                  Achieved {format(new Date(entry.achievedAt), "MMM d, yyyy")}
                </p>
                {entry.revokedAt ? (
                  <p className="text-sm text-muted-foreground">
                    Revoked {format(new Date(entry.revokedAt), "MMM d, yyyy")}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
