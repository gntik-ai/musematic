"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { AlertTriangle, Trash2 } from "lucide-react";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { ConfirmDeleteDialog } from "@/components/features/data-lifecycle/ConfirmDeleteDialog";
import { DeletionGraceBanner } from "@/components/features/data-lifecycle/DeletionGraceBanner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useRequestWorkspaceDeletion,
  useWorkspaceDeletionJob,
} from "@/lib/hooks/use-data-lifecycle";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function WorkspaceDeletePage() {
  const params = useParams<{ id: string }>();
  const workspace = useWorkspaceStore((state) => state.currentWorkspace);
  const workspaceName = workspace?.name ?? params.id;

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const requestDeletion = useRequestWorkspaceDeletion(params.id);
  const job = useWorkspaceDeletionJob(params.id, activeJobId);

  const submittedJob = requestDeletion.data ?? job.data ?? null;

  return (
    <WorkspaceOwnerLayout
      title="Delete workspace"
      description="Permanently remove this workspace and all of its data."
    >
      {submittedJob ? <DeletionGraceBanner job={submittedJob} /> : null}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Danger zone
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <Alert>
            <AlertTitle>What happens next</AlertTitle>
            <AlertDescription>
              <ul className="ml-4 list-disc space-y-1">
                <li>Workspace becomes inaccessible immediately.</li>
                <li>You receive an email with a 7-day cancel link.</li>
                <li>
                  After the grace period: agents, executions, costs, and members
                  are deleted. Audit history is retained as a 90-day tombstone.
                </li>
              </ul>
            </AlertDescription>
          </Alert>
          {requestDeletion.isError ? (
            <Alert variant="destructive">
              <AlertTitle>Could not schedule deletion</AlertTitle>
              <AlertDescription>
                {requestDeletion.error?.message ?? "Please try again."}
              </AlertDescription>
            </Alert>
          ) : null}
          <ConfirmDeleteDialog
            workspaceName={workspaceName}
            isPending={requestDeletion.isPending}
            onConfirm={(vars) =>
              requestDeletion.mutate(vars, {
                onSuccess: (createdJob) => setActiveJobId(createdJob.id),
              })
            }
            trigger={
              <Button variant="destructive" disabled={Boolean(submittedJob)}>
                <Trash2 className="mr-2 h-4 w-4" />
                Delete workspace…
              </Button>
            }
          />
        </CardContent>
      </Card>
    </WorkspaceOwnerLayout>
  );
}
