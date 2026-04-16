"use client";

import { format } from "date-fns";
import { EmptyState } from "@/components/shared/EmptyState";
import { ScoreGauge } from "@/components/shared/ScoreGauge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  CONTEXT_SOURCE_LABELS,
  type ContextQualityView,
} from "@/lib/types/operator-dashboard";

export interface ContextQualityPanelProps {
  quality: ContextQualityView | undefined;
  isLoading: boolean;
}

function toneForScore(score: number): string {
  if (score < 50) {
    return "border-destructive/30 bg-destructive/10 text-foreground";
  }
  if (score < 75) {
    return "border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300";
  }

  return "border-emerald-500/30 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300";
}

export function ContextQualityPanel({
  quality,
  isLoading,
}: ContextQualityPanelProps) {
  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle>Context quality</CardTitle>
        <p className="text-sm text-muted-foreground">
          Source provenance and quality weighting for the selected execution.
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {isLoading ? (
          <Skeleton className="h-[320px] rounded-xl" />
        ) : !quality ? (
          <EmptyState
            description="Context quality data is not available."
            title="Context quality unavailable"
          />
        ) : (
          <>
            <div className="flex justify-center">
              <ScoreGauge
                label="Overall quality"
                score={quality.overallQualityScore}
                size={160}
                valueLabel={`${quality.overallQualityScore}`}
              />
            </div>

            {quality.sources.length === 0 ? (
              <EmptyState
                description="Full provenance unavailable"
                title="Scalar context quality only"
              />
            ) : (
              <div className="overflow-hidden rounded-xl border border-border/60">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-left">
                    <tr>
                      <th className="px-4 py-3 font-medium">Source</th>
                      <th className="px-4 py-3 font-medium">Quality</th>
                      <th className="px-4 py-3 font-medium">Weight</th>
                      <th className="px-4 py-3 font-medium">Provenance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quality.sources.map((source) => (
                      <tr key={source.id} className="border-t border-border/60">
                        <td className="px-4 py-3">
                          {CONTEXT_SOURCE_LABELS[source.sourceType]}
                        </td>
                        <td className="px-4 py-3">
                          <Badge className={toneForScore(source.qualityScore)} variant="outline">
                            {source.qualityScore}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          {(source.contributionWeight * 100).toFixed(0)}%
                        </td>
                        <td className="px-4 py-3">
                          {source.provenanceRef ? (
                            <a
                              className="text-brand-accent underline-offset-4 hover:underline"
                              href={source.provenanceRef}
                            >
                              Open source
                            </a>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <p className="text-xs text-muted-foreground">
              Assembled {format(new Date(quality.assembledAt), "PPp")}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
