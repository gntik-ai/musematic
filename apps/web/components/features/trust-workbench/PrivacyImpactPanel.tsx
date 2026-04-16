"use client";

import { differenceInHours, format, formatDistanceToNow, parseISO } from "date-fns";
import { Clock3 } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { usePrivacyImpact } from "@/lib/hooks/use-privacy-impact";
import { useToast } from "@/lib/hooks/use-toast";
import { PrivacyDataCategoryRow } from "@/components/features/trust-workbench/PrivacyDataCategoryRow";

export interface PrivacyImpactPanelProps {
  agentId: string;
}

export function PrivacyImpactPanel({ agentId }: PrivacyImpactPanelProps) {
  const { toast } = useToast();
  const privacyImpactQuery = usePrivacyImpact(agentId);

  if (privacyImpactQuery.isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-28 rounded-[1.5rem]" />
        ))}
      </div>
    );
  }

  if (privacyImpactQuery.isError || !privacyImpactQuery.data) {
    return (
      <EmptyState
        description="The latest privacy analysis could not be loaded."
        title="Privacy analysis not available"
      />
    );
  }

  const analysis = privacyImpactQuery.data;
  const ageHours = differenceInHours(new Date(), parseISO(analysis.analysisTimestamp));
  const isStale = ageHours > 24;

  return (
    <div className="space-y-4">
      <div className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">Privacy impact analysis</h3>
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock3 className="h-4 w-4" />
              {format(parseISO(analysis.analysisTimestamp), "PPp")} (
              {formatDistanceToNow(parseISO(analysis.analysisTimestamp), {
                addSuffix: true,
              })}
              )
            </p>
            <p className="text-sm text-muted-foreground">
              Sources: {analysis.dataSources.join(", ") || "None reported"}
            </p>
          </div>

          {analysis.overallCompliant ? (
            <Alert className="max-w-md">
              <AlertTitle>No privacy concerns identified.</AlertTitle>
              <AlertDescription>
                This analysis did not surface any category-level privacy violations.
              </AlertDescription>
            </Alert>
          ) : null}
        </div>
      </div>

      {isStale ? (
        <Alert>
          <AlertTitle>Analysis is {ageHours} hours old</AlertTitle>
          <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>Request a fresh assessment if recent changes may have altered data handling.</span>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                toast({
                  title: "Request re-analysis",
                  description: "Contact the agent owner to re-trigger privacy analysis.",
                })
              }
            >
              Request Re-analysis
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="space-y-3">
        {analysis.categories.map((category) => (
          <PrivacyDataCategoryRow key={category.name} category={category} />
        ))}
      </div>
    </div>
  );
}
