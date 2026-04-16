"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ServiceHealthIndicator } from "@/components/features/operator/ServiceHealthIndicator";
import {
  SERVICE_GROUP_ORDER,
  type ServiceHealthSnapshot,
  type ServiceStatus,
} from "@/lib/types/operator-dashboard";

export interface ServiceHealthPanelProps {
  snapshot: ServiceHealthSnapshot | undefined;
  isLoading: boolean;
}

const overallTone: Record<ServiceStatus, string> = {
  healthy:
    "border-emerald-500/30 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300",
  degraded:
    "border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300",
  unhealthy: "border-rose-500/30 bg-rose-500/12 text-rose-700 dark:text-rose-300",
  unknown: "border-border/80 bg-muted/70 text-muted-foreground",
};

export function ServiceHealthPanel({
  snapshot,
  isLoading,
}: ServiceHealthPanelProps) {
  const services = snapshot?.services ?? [];
  const isEntry = (
    entry: (typeof services)[number] | undefined,
  ): entry is (typeof services)[number] => Boolean(entry);
  const dataStores = SERVICE_GROUP_ORDER.data_store
    .map((key) => services.find((entry) => entry.serviceKey === key))
    .filter(isEntry);
  const satellites = SERVICE_GROUP_ORDER.satellite
    .map((key) => services.find((entry) => entry.serviceKey === key))
    .filter(isEntry);

  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <CardTitle>Service health</CardTitle>
          <p className="text-sm text-muted-foreground">
            Backend stores and satellite services monitored from the shared health
            profile.
          </p>
        </div>
        <Badge
          className={overallTone[snapshot?.overallStatus ?? "unknown"]}
          variant="outline"
        >
          {snapshot?.overallStatus ?? "unknown"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-6">
        <section className="space-y-3">
          <div>
            <h3 className="font-medium">Data stores</h3>
            <p className="text-sm text-muted-foreground">
              Operational status for primary persistence and indexing systems.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {isLoading
              ? Array.from({ length: 8 }).map((_, index) => (
                  <Skeleton key={`store-${index}`} className="h-20 rounded-xl" />
                ))
              : dataStores.map((entry) => (
                  <ServiceHealthIndicator key={entry.serviceKey} entry={entry} />
                ))}
          </div>
        </section>

        <section className="space-y-3">
          <div>
            <h3 className="font-medium">Satellite services</h3>
            <p className="text-sm text-muted-foreground">
              Runtime and orchestration services that support execution and monitoring.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {isLoading
              ? Array.from({ length: 4 }).map((_, index) => (
                  <Skeleton
                    key={`satellite-${index}`}
                    className="h-20 rounded-xl"
                  />
                ))
              : satellites.map((entry) => (
                  <ServiceHealthIndicator key={entry.serviceKey} entry={entry} />
                ))}
          </div>
        </section>
      </CardContent>
    </Card>
  );
}
