"use client";

import { useState } from "react";
import { Download, FileArchive, Loader2 } from "lucide-react";
import type { ExportJob } from "@/lib/api/data-lifecycle";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRequestTenantExport } from "@/lib/hooks/use-data-lifecycle";

export function TenantExportPanel({ tenantId }: { tenantId: string }) {
  const [job, setJob] = useState<ExportJob | null>(null);
  const requestExport = useRequestTenantExport(tenantId);

  const handleRequest = () => {
    requestExport.mutate(undefined, { onSuccess: setJob });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileArchive className="h-5 w-5" />
          Tenant data export
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p>
          Generate a password-protected ZIP containing all workspaces, users,
          and audit chain entries for this tenant. The download password is
          delivered to the tenant admin out-of-band.
        </p>
        <Button onClick={handleRequest} disabled={requestExport.isPending}>
          {requestExport.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Download className="mr-2 h-4 w-4" />
          )}
          Request tenant export
        </Button>
        {requestExport.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Export request failed</AlertTitle>
            <AlertDescription>
              {requestExport.error?.message ?? "Please try again."}
            </AlertDescription>
          </Alert>
        ) : null}
        {job ? (
          <div className="rounded-md border p-4">
            <div className="flex items-center gap-2">
              <Badge>{job.status}</Badge>
              <span className="text-xs text-muted-foreground">
                requested {new Date(job.requested_at).toLocaleString()}
              </span>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              The password will be delivered to the tenant admin separately.
              The download URL stays valid for 7 days.
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
