"use client";

import { ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDPAMetadata } from "@/lib/hooks/use-data-lifecycle";
import { Article28Button } from "./Article28Button";
import { DPAUploadDialog } from "./DPAUploadDialog";

export function DPAMetadataPanel({ tenantId }: { tenantId: string }) {
  const { data, isLoading } = useDPAMetadata(tenantId);

  if (isLoading) return <Skeleton className="h-64 rounded-md" />;
  const active = data?.active ?? null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            Data Processing Agreement
          </CardTitle>
        </div>
        <DPAUploadDialog tenantId={tenantId} />
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {active ? (
          <div className="rounded-md border p-4">
            <div className="flex items-center gap-2">
              <Badge>{active.version}</Badge>
              <span className="text-xs text-muted-foreground">
                signed {new Date(active.signed_at).toLocaleDateString()}
              </span>
            </div>
            <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
              SHA-256 {active.sha256}
            </p>
            {active.vault_path ? (
              <p className="mt-1 text-xs text-muted-foreground">
                Vault path:{" "}
                <span className="font-mono">{active.vault_path}</span>
              </p>
            ) : null}
          </div>
        ) : (
          <p className="text-muted-foreground">
            No DPA uploaded yet. Default tenants use the standard clickwrap DPA.
          </p>
        )}
        {data?.history && data.history.length > 0 ? (
          <p className="text-xs text-muted-foreground">
            {data.history.length} historical version
            {data.history.length === 1 ? "" : "s"} preserved.
          </p>
        ) : null}
        <Article28Button tenantId={tenantId} />
      </CardContent>
    </Card>
  );
}
