"use client";

import { useMemo, useState } from "react";
import { GitCompare } from "lucide-react";
import { PlanVersionDiff } from "@/components/features/admin/PlanVersionDiff";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminPlanVersions, type PlanVersion } from "@/lib/hooks/use-admin-plans";

interface PlanVersionHistoryProps {
  slug: string;
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "None";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function priorVersion(versions: PlanVersion[], version: PlanVersion): PlanVersion | null {
  const sorted = [...versions].sort((left, right) => left.version - right.version);
  const index = sorted.findIndex((item) => item.version === version.version);
  return index > 0 ? sorted[index - 1] ?? null : null;
}

export function PlanVersionHistory({ slug }: PlanVersionHistoryProps) {
  const { data, error, isLoading } = useAdminPlanVersions(slug);
  const versions = data?.items ?? [];
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [compareFrom, setCompareFrom] = useState<number | null>(null);
  const [compareTo, setCompareTo] = useState<number | null>(null);

  const selected = useMemo(
    () => versions.find((version) => version.version === selectedVersion) ?? null,
    [selectedVersion, versions],
  );
  const fromVersion = versions.find((version) => version.version === compareFrom) ?? null;
  const toVersion = versions.find((version) => version.version === compareTo) ?? null;

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Plan versions unavailable</AlertTitle>
        <AlertDescription>
          {error instanceof Error ? error.message : "Version history could not be loaded"}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-4">
      <section className="rounded-md border p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <GitCompare className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Compare versions</h2>
        </div>
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
          <Select
            aria-label="Previous version"
            value={compareFrom ?? ""}
            onChange={(event) => setCompareFrom(Number(event.target.value) || null)}
          >
            <option value="">Previous version</option>
            {versions.map((version) => (
              <option key={version.id} value={version.version}>
                v{version.version}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Selected version"
            value={compareTo ?? ""}
            onChange={(event) => setCompareTo(Number(event.target.value) || null)}
          >
            <option value="">Selected version</option>
            {versions.map((version) => (
              <option key={version.id} value={version.version}>
                v{version.version}
              </option>
            ))}
          </Select>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              const newest = versions[0] ?? null;
              setCompareTo(newest?.version ?? null);
              setCompareFrom(newest ? priorVersion(versions, newest)?.version ?? null : null);
            }}
          >
            Latest diff
          </Button>
        </div>
        {fromVersion && toVersion ? (
          <div className="mt-4">
            <PlanVersionDiff fromVersion={fromVersion} toVersion={toVersion} />
          </div>
        ) : null}
      </section>

      <div className="space-y-3">
        {versions.map((version) => {
          const isOpen = selected?.version === version.version;
          return (
            <section key={version.id} className="rounded-md border p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge variant={version.deprecated_at ? "outline" : "default"}>
                      v{version.version}
                    </Badge>
                    <Badge variant="secondary">
                      {version.subscription_count ?? 0} subscriptions
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Published {formatDate(version.published_at)} · Deprecated{" "}
                    {formatDate(version.deprecated_at)}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedVersion(isOpen ? null : version.version)}
                >
                  {isOpen ? "Hide diff" : "Show diff against prior"}
                </Button>
              </div>
              {isOpen ? (
                <div className="mt-4">
                  <PlanVersionDiff
                    fromVersion={priorVersion(versions, version)}
                    toVersion={version}
                  />
                </div>
              ) : null}
            </section>
          );
        })}
      </div>

      {versions.length === 0 ? (
        <div className="rounded-md border p-6 text-sm text-muted-foreground">
          No versions have been published.
        </div>
      ) : null}
    </div>
  );
}
