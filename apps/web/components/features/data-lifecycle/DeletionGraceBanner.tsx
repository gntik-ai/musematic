"use client";

import { AlertTriangle } from "lucide-react";
import type { DeletionJob } from "@/lib/api/data-lifecycle";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function DeletionGraceBanner({ job }: { job: DeletionJob }) {
  if (job.phase !== "phase_1") return null;
  const ends = new Date(job.grace_ends_at);
  return (
    <Alert variant="destructive">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>Pending deletion</AlertTitle>
      <AlertDescription>
        This workspace is scheduled for deletion at{" "}
        {ends.toLocaleString()}. Use the cancel link emailed to the owner to
        abort the deletion before the grace period ends.
      </AlertDescription>
    </Alert>
  );
}
