"use client";

import Link from "next/link";
import { Workflow } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { WorkflowEditorShell } from "@/components/features/workflows/editor/WorkflowEditorShell";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function NewWorkflowEditorMonitorPage() {
  const currentWorkspace = useWorkspaceStore((state) => state.currentWorkspace);
  const userWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspace?.id ?? userWorkspaceId;

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before creating a workflow."
        icon={Workflow}
        title="Choose a workspace"
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link
          className="inline-flex text-sm font-medium text-brand-primary transition hover:text-brand-primary/80"
          href="/workflow-editor-monitor"
        >
          Back to workflows
        </Link>
        <div>
          <h1 className="text-3xl font-semibold">New workflow</h1>
          <p className="mt-2 max-w-2xl text-muted-foreground">
            Start from an empty YAML canvas. Once the definition has a top-level
            name, you can create the workflow in the current workspace.
          </p>
        </div>
      </div>

      <WorkflowEditorShell />
    </div>
  );
}
