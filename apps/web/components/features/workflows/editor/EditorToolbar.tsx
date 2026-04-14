"use client";

import { useMemo } from "react";
import { Save, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCreateWorkflow, useUpdateWorkflow } from "@/lib/hooks/use-workflow-save";
import { toast } from "@/lib/hooks/use-toast";
import { useWorkflowEditorStore } from "@/lib/stores/workflow-editor-store";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";
import { cn } from "@/lib/utils";
import { ApiError } from "@/types/api";

interface EditorToolbarProps {
  workflowId?: string | null;
  versionNumber?: number | null;
  className?: string;
}

function readYamlField(yamlContent: string, fieldName: string): string | null {
  const match = yamlContent.match(
    new RegExp(`^${fieldName}:\\s*(.+)$`, "m"),
  );

  return match?.[1]?.trim().replace(/^["']|["']$/g, "") ?? null;
}

function getSaveErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "The workflow could not be saved.";
}

export function EditorToolbar({
  workflowId = null,
  versionNumber = null,
  className,
}: EditorToolbarProps) {
  const router = useRouter();
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const userWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const yamlContent = useWorkflowEditorStore((state) => state.yamlContent);
  const validationErrors = useWorkflowEditorStore(
    (state) => state.validationErrors,
  );
  const isDirty = useWorkflowEditorStore((state) => state.isDirty);
  const isSaving = useWorkflowEditorStore((state) => state.isSaving);
  const lastSavedVersionId = useWorkflowEditorStore(
    (state) => state.lastSavedVersionId,
  );
  const setIsSaving = useWorkflowEditorStore((state) => state.setIsSaving);
  const markSaved = useWorkflowEditorStore((state) => state.markSaved);
  const createWorkflow = useCreateWorkflow();
  const updateWorkflow = useUpdateWorkflow();

  const workspaceId = currentWorkspaceId ?? userWorkspaceId;
  const validationErrorCount = validationErrors.filter(
    (error) => error.severity === "error",
  ).length;
  const warningCount = validationErrors.length - validationErrorCount;
  const isPending = isSaving || createWorkflow.isPending || updateWorkflow.isPending;

  const saveLabel = useMemo(() => {
    if (isPending) {
      return workflowId ? "Saving..." : "Creating...";
    }

    return workflowId ? "Save Changes" : "Create Workflow";
  }, [isPending, workflowId]);

  return (
    <div
      className={cn(
        "flex flex-col gap-4 rounded-2xl border border-border/60 bg-card/80 px-4 py-4 shadow-sm md:flex-row md:items-center md:justify-between",
        className,
      )}
    >
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">
            {workflowId ? `Version ${versionNumber ?? "..."}` : "New workflow"}
          </Badge>
          {validationErrorCount > 0 ? (
            <Badge variant="destructive">
              {validationErrorCount} validation{" "}
              {validationErrorCount === 1 ? "error" : "errors"}
            </Badge>
          ) : null}
          {warningCount > 0 ? (
            <Badge className="bg-[hsl(var(--warning)/0.16)] text-[hsl(var(--warning))]" variant="outline">
              {warningCount} warning{warningCount === 1 ? "" : "s"}
            </Badge>
          ) : null}
          {isDirty ? (
            <Badge className="bg-[hsl(var(--brand-accent)/0.14)] text-[hsl(var(--brand-accent))]" variant="outline">
              Unsaved changes
            </Badge>
          ) : lastSavedVersionId ? (
            <Badge className="bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))]" variant="outline">
              Saved
            </Badge>
          ) : null}
        </div>
        <p className="text-sm text-muted-foreground">
          Save creates a new workflow version and refreshes the current editor
          state from the backend.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          disabled={!isDirty || isPending || (!workflowId && !workspaceId)}
          onClick={async () => {
            if (!yamlContent.trim()) {
              toast({
                title: "Workflow YAML is empty",
                description: "Add a workflow definition before saving.",
                variant: "destructive",
              });
              return;
            }

            const name = readYamlField(yamlContent, "name");
            const description = readYamlField(yamlContent, "description");

            if (!workflowId && !workspaceId) {
              toast({
                title: "Workspace required",
                description: "Select a workspace before creating a workflow.",
                variant: "destructive",
              });
              return;
            }

            if (!name) {
              toast({
                title: "Workflow name missing",
                description: "Add a top-level `name:` field to the YAML before saving.",
                variant: "destructive",
              });
              return;
            }

            setIsSaving(true);

            try {
              const workflow = workflowId
                ? await updateWorkflow.mutateAsync({
                    workflowId,
                    yamlContent,
                    description,
                  })
                : await createWorkflow.mutateAsync({
                    workspaceId: workspaceId ?? "",
                    name,
                    description,
                    yamlContent,
                  });

              markSaved(workflow.currentVersionId);
              toast({
                title: workflowId ? "Workflow saved" : "Workflow created",
                description: workflowId
                  ? `${workflow.name} is now on version ${workflow.currentVersionNumber}.`
                  : `${workflow.name} is ready for further editing.`,
                variant: "success",
              });

              if (!workflowId) {
                router.push(`/workflow-editor-monitor/${workflow.id}`);
              }
            } catch (error) {
              setIsSaving(false);
              toast({
                title: "Save failed",
                description: getSaveErrorMessage(error),
                variant: "destructive",
              });
            }
          }}
        >
          <Save className="h-4 w-4" />
          {saveLabel}
        </Button>

        <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-background/80 px-3 py-2 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 text-[hsl(var(--brand-accent))]" />
          Graph preview refreshes 500ms after typing stops
        </div>
      </div>
    </div>
  );
}
