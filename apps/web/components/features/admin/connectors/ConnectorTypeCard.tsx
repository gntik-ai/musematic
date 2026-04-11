"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import { useConnectorTypeToggleMutation } from "@/lib/hooks/use-admin-settings";
import type { ConnectorTypeGlobalConfig } from "@/lib/types/admin";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

export function ConnectorTypeCard({
  config,
}: {
  config: ConnectorTypeGlobalConfig;
}) {
  const mutation = useConnectorTypeToggleMutation(config.slug);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="space-y-1">
          <CardTitle className="text-base">{config.display_name}</CardTitle>
          <CardDescription>{config.description}</CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {mutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          ) : null}
          <Switch
            aria-label={`Toggle ${config.display_name}`}
            checked={config.is_enabled}
            disabled={mutation.isPending}
            onCheckedChange={(checked) => mutation.mutate(checked)}
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <Badge variant="outline">
            {config.max_payload_size_bytes.toLocaleString()} byte payload
          </Badge>
          <Badge variant="outline">
            {config.default_retry_count} default retries
          </Badge>
        </div>
        {!config.is_enabled && config.active_instance_count > 0 ? (
          <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-300">
            <AlertTriangle className="h-4 w-4" />
            <Badge className="gap-1" variant="destructive">
              {config.active_instance_count} active instances
            </Badge>
          </div>
        ) : (
          <Badge variant="outline">
            {config.active_instance_count} active instances
          </Badge>
        )}
      </CardContent>
    </Card>
  );
}
