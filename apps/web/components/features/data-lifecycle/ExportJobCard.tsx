"use client";

import { useState } from "react";
import { Download, FileArchive, Loader2 } from "lucide-react";
import type { ExportJob } from "@/lib/api/data-lifecycle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useRequestWorkspaceExport,
  useWorkspaceExportJob,
  useWorkspaceExportJobs,
} from "@/lib/hooks/use-data-lifecycle";

function formatBytes(bytes?: number | null): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let value = bytes;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(1)} ${units[i]}`;
}

function statusVariant(status: ExportJob["status"]): "secondary" | "default" | "destructive" {
  if (status === "completed") return "default";
  if (status === "failed") return "destructive";
  return "secondary";
}

export function ExportJobCard({ workspaceId }: { workspaceId: string }) {
  const jobs = useWorkspaceExportJobs(workspaceId, { limit: 10 });
  const requestExport = useRequestWorkspaceExport(workspaceId);
  const [requestedJobId, setRequestedJobId] = useState<string | null>(null);
  const polledJob = useWorkspaceExportJob(workspaceId, requestedJobId);

  const items = jobs.data?.items ?? [];
  const activeRemoteJob = items.find(
    (j) => j.status === "pending" || j.status === "processing",
  );
  const activeJob = polledJob.data ?? activeRemoteJob ?? null;

  const handleRequest = () => {
    requestExport.mutate(undefined, {
      onSuccess: (job) => {
        setRequestedJobId(job.id);
      },
    });
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <FileArchive className="h-5 w-5" />
            Workspace data export
          </CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Download a complete archive of this workspace. The archive is a ZIP
            file with structured JSON files per resource type and is available
            for 7 days from a signed URL delivered by email.
          </p>
        </div>
        <Button
          onClick={handleRequest}
          disabled={requestExport.isPending || Boolean(activeJob)}
        >
          {requestExport.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          <span className="ml-2">Request export</span>
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {jobs.isLoading ? (
          <Skeleton className="h-24 rounded-md" />
        ) : null}
        {!jobs.isLoading && items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No export jobs yet. Click "Request export" to start one.
          </p>
        ) : null}
        {items.map((job) => (
          <div
            key={job.id}
            className="flex flex-col gap-2 rounded-md border p-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
                <span className="text-sm text-muted-foreground">
                  {new Date(job.requested_at).toLocaleString()}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {formatBytes(job.output_size_bytes)} •{" "}
                {job.output_expires_at
                  ? `Expires ${new Date(job.output_expires_at).toLocaleDateString()}`
                  : "—"}
              </p>
              {job.error_message ? (
                <p className="text-xs text-destructive">{job.error_message}</p>
              ) : null}
            </div>
            {job.output_url && job.status === "completed" ? (
              <Button asChild size="sm" variant="outline">
                <a href={job.output_url} target="_blank" rel="noreferrer">
                  <Download className="mr-2 h-4 w-4" />
                  Download
                </a>
              </Button>
            ) : null}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
