"use client";

import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { fleetApi } from "@/lib/hooks/use-fleets";
import { useGovernanceChain, useGovernanceChainMutations } from "@/lib/hooks/use-governance-chain";
import { useWorkspaceStore } from "@/store/workspace-store";
import type { GovernanceChain } from "@/types/governance";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface GovernanceChainEditorProps {
  scope: { kind: "workspace"; workspaceId: string } | { kind: "fleet"; fleetId: string };
}

function EmptyCopy({ label }: { label: string }) {
  return <p className="text-sm text-muted-foreground">No {label} assigned — default applies.</p>;
}

export function GovernanceChainEditor({ scope }: GovernanceChainEditorProps) {
  const workspaceId =
    scope.kind === "workspace"
      ? scope.workspaceId
      : useWorkspaceStore.getState().currentWorkspace?.id ?? null;
  const chainQuery = useGovernanceChain(scope.kind === "workspace" ? scope.workspaceId : null);
  const mutation = useGovernanceChainMutations(scope.kind === "workspace" ? scope.workspaceId : null);
  const [draft, setDraft] = useState<GovernanceChain | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if (chainQuery.data) {
      setDraft(chainQuery.data);
    }
  }, [chainQuery.data]);

  const saveFleetChain = async () => {
    if (!draft || scope.kind !== "fleet") {
      return;
    }
    await fleetApi.put(`/api/v1/fleets/${scope.fleetId}/governance-chain`, {
      observer_fqns: draft.observerAgentFqn ? [draft.observerAgentFqn] : [],
      judge_fqns: draft.judgeAgentFqn ? [draft.judgeAgentFqn] : [],
      enforcer_fqns: draft.enforcerAgentFqn ? [draft.enforcerAgentFqn] : [],
      policy_binding_ids: [],
    });
  };

  const handleSave = async () => {
    if (!draft) {
      return;
    }
    if (scope.kind === "workspace") {
      mutation.mutate(draft, { onSuccess: () => setConfirmOpen(false) });
      return;
    }
    await saveFleetChain();
    setConfirmOpen(false);
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 text-brand-accent">
            <ShieldCheck className="h-4 w-4" />
            <span className="text-sm font-semibold uppercase tracking-[0.2em]">Governance chain</span>
          </div>
          <CardTitle>
            {scope.kind === "workspace" ? "Workspace governance" : "Fleet governance"}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          {([
            { field: "observerAgentFqn", label: "Observer" },
            { field: "judgeAgentFqn", label: "Judge" },
            { field: "enforcerAgentFqn", label: "Enforcer" },
          ] as const).map(({ field, label }) => {
            const value = draft?.[field] as string | null | undefined;
            return (
              <Card key={field} className="border-dashed">
                <CardHeader>
                  <CardTitle className="text-base">{label}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Input
                    placeholder={`agent namespace:fqn for ${label.toLowerCase()}`}
                    value={value ?? ""}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...(current ?? {
                          workspaceId: workspaceId ?? "",
                          observerAgentFqn: null,
                          judgeAgentFqn: null,
                          enforcerAgentFqn: null,
                          updatedAt: new Date().toISOString(),
                          updatedBy: "current-user",
                        }),
                        [field]: event.target.value || null,
                      }))
                    }
                  />
                  {value ? <p className="text-sm text-muted-foreground">Assigned: {value}</p> : <EmptyCopy label={label.toLowerCase()} />}
                </CardContent>
              </Card>
            );
          })}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button disabled={!draft} onClick={() => setConfirmOpen(true)}>
          Save governance chain
        </Button>
      </div>

      <ConfirmDialog
        confirmLabel="Save"
        description="Save this governance chain configuration? Empty roles will continue to use inherited defaults."
        isLoading={mutation.isPending}
        open={confirmOpen}
        title="Confirm governance update"
        onConfirm={() => void handleSave()}
        onOpenChange={setConfirmOpen}
      />
    </div>
  );
}
