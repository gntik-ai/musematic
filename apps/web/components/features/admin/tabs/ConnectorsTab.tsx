"use client";

import { ConnectorTypeCard } from "@/components/features/admin/connectors/ConnectorTypeCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useConnectorTypeConfigs } from "@/lib/hooks/use-admin-settings";

export function ConnectorsTab() {
  const query = useConnectorTypeConfigs();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Connectors</CardTitle>
        <p className="text-sm text-muted-foreground">
          Enable or disable connector types globally. Changes save immediately.
        </p>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        {query.isLoading
          ? Array.from({ length: 4 }).map((_, index) => (
              <Card key={index}>
                <CardHeader>
                  <Skeleton className="h-5 w-40" />
                  <Skeleton className="h-4 w-full" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-8 w-28" />
                </CardContent>
              </Card>
            ))
          : (query.data ?? []).map((config) => (
              <ConnectorTypeCard key={config.slug} config={config} />
            ))}
      </CardContent>
    </Card>
  );
}
