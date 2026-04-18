"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { CreateEvalSuiteForm } from "@/components/features/eval/CreateEvalSuiteForm";
import { EmptyState } from "@/components/shared/EmptyState";
import { FlaskConical } from "lucide-react";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function CreateEvalSuitePage() {
  const router = useRouter();
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before creating a suite."
        icon={FlaskConical}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <Link className="text-sm text-muted-foreground underline-offset-4 hover:underline" href="/evaluation-testing">
          Back to Eval Suites
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">Create Eval Suite</h1>
      </div>
      <CreateEvalSuiteForm
        workspaceId={workspaceId}
        onSuccess={(evalSetId) =>
          router.push(`/evaluation-testing/${encodeURIComponent(evalSetId)}`)
        }
      />
    </section>
  );
}
