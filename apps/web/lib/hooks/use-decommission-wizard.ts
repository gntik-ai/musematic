"use client";

import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppMutation } from "@/lib/hooks/use-api";
import { useAgent } from "@/lib/hooks/use-agents";
import type { DecommissionPlan } from "@/types/operator";
import type { AgentDetail } from "@/lib/types/agent-management";

const registryApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export type DecommissionWizardStage =
  | "idle"
  | "warning"
  | "dry_run"
  | "submitting"
  | "done";

function buildPlan(agent: AgentDetail | undefined): DecommissionPlan | null {
  if (!agent) {
    return null;
  }
  return {
    agentFqn: agent.fqn,
    dependencies: [
      `${agent.namespace}:shared-policies`,
      `${agent.namespace}:runtime-dependents`,
    ],
    dryRunSummary: [
      `Status will transition from ${agent.status} to decommissioned.`,
      `${agent.visibility_patterns.length} visibility grants may need review.`,
      `Latest revision ${agent.latest_revision_number} will remain discoverable for audits.`,
    ],
  };
}

export function useDecommissionWizard(agentId: string) {
  const queryClient = useQueryClient();
  const agentQuery = useAgent(agentId);
  const [stage, setStage] = useState<DecommissionWizardStage>("idle");
  const [confirmFqn, setConfirmFqn] = useState("");
  const plan = useMemo(() => buildPlan(agentQuery.data), [agentQuery.data]);

  const mutation = useAppMutation<void, void>(
    async () => {
      if (!agentQuery.data?.workspace_id) {
        throw new Error("Workspace unavailable for decommission request");
      }
      await registryApi.post(
        `/api/v1/registry/${encodeURIComponent(agentQuery.data.workspace_id)}/agents/${encodeURIComponent(agentId)}/decommission`,
        {
          reason: "Decommission requested from operator dashboard",
        },
      );
    },
    {
      onMutate: async () => {
        setStage("submitting");
      },
      invalidateKeys: [
        ["agent", agentId],
        ["marketplace-agents"],
      ],
      onSuccess: async () => {
        await queryClient.invalidateQueries({ queryKey: ["agent-management"] });
        setStage("done");
      },
    },
  );

  const advance = () => {
    setStage((current) => {
      if (current === "idle") {
        return "warning";
      }
      if (current === "warning") {
        return "dry_run";
      }
      return current;
    });
  };

  const cancel = () => {
    setStage("idle");
    setConfirmFqn("");
  };

  const confirm = async () => {
    await mutation.mutateAsync();
  };

  return {
    stage,
    plan,
    advance,
    cancel,
    confirm,
    confirmFqn,
    setConfirmFqn,
    isLoading: mutation.isPending,
  };
}
