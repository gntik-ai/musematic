"use client";

import { useState } from "react";
import { PackageOpen, Sparkles, UploadCloud } from "lucide-react";
import { AgentDataTable } from "@/components/features/agent-management/AgentDataTable";
import { AgentUploadZone } from "@/components/features/agent-management/AgentUploadZone";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";
import { useRouter } from "next/navigation";

export default function AgentManagementPage() {
  const router = useRouter();
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before browsing the agent catalog."
        icon={PackageOpen}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <div className="rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
              <Sparkles className="h-4 w-4" />
              Agent management
            </div>
            <div>
              <h1 className="text-3xl font-semibold">Agent catalog workbench</h1>
              <p className="mt-2 max-w-3xl text-muted-foreground">
                Browse agents, inspect lifecycle status, and move into deeper management workflows from one catalog.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button className="gap-2" type="button" variant="secondary" onClick={() => router.push("/agent-management/wizard")}>
              <Sparkles className="h-4 w-4" />
              Compose with AI
            </Button>
            <Dialog open={uploadDialogOpen} onOpenChange={setUploadDialogOpen}>
              <DialogTrigger asChild>
                <Button className="gap-2">
                  <UploadCloud className="h-4 w-4" />
                  Upload package
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-xl space-y-4">
                <div>
                  <h2 className="text-xl font-semibold">Upload package</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Create a new draft agent by uploading a signed package bundle.
                  </p>
                </div>
                <AgentUploadZone
                  workspace_id={workspaceId}
                  onUploadComplete={() => {
                    setUploadDialogOpen(false);
                  }}
                />
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      <AgentDataTable workspace_id={workspaceId} />
    </section>
  );
}
