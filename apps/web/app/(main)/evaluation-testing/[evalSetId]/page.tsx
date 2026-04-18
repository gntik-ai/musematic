"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AdversarialTestReviewModal,
} from "@/components/features/eval/AdversarialTestReviewModal";
import { EvalRunList } from "@/components/features/eval/EvalRunList";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useEvalSet } from "@/lib/hooks/use-eval-sets";
import { useEvalMutations } from "@/lib/hooks/use-eval-mutations";
import { useEvalRuns } from "@/lib/hooks/use-eval-runs";
import { useAteConfigs } from "@/lib/hooks/use-ate";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

interface EvalSuiteDetailPageProps {
  params: Promise<{
    evalSetId: string;
  }>;
}

export default function EvalSuiteDetailPage({ params }: EvalSuiteDetailPageProps) {
  const { evalSetId } = use(params);
  const router = useRouter();
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const evalSetQuery = useEvalSet(evalSetId);
  const runsQuery = useEvalRuns(workspaceId ?? "", evalSetId);
  const ateConfigsQuery = useAteConfigs(workspaceId ?? "");
  const { runEval } = useEvalMutations();
  const [selectedRunId, setSelectedRunId] = useState<string | undefined>(undefined);
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  const [agentFqn, setAgentFqn] = useState("");
  const [adversarialModalOpen, setAdversarialModalOpen] = useState(false);

  useEffect(() => {
    if (runsQuery.data?.items[0]?.agent_fqn && !agentFqn) {
      setAgentFqn(runsQuery.data.items[0].agent_fqn);
    }
  }, [agentFqn, runsQuery.data]);

  const selectedSuite = evalSetQuery.data;
  const selectedRunIdsArray = useMemo(() => Array.from(selectedRunIds), [selectedRunIds]);

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before browsing suite details."
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
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight">
              {selectedSuite?.name ?? "Eval Suite Detail"}
            </h1>
            <p className="max-w-3xl text-sm text-muted-foreground">
              {selectedSuite?.description ?? "Benchmark run history and verdict drill-down for this suite."}
            </p>
            <p className="text-sm text-muted-foreground">
              Pass threshold:{" "}
              {typeof selectedSuite?.pass_threshold === "number"
                ? `${Math.round(selectedSuite.pass_threshold * 100)}%`
                : "—"}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Popover>
              <PopoverTrigger asChild>
                <Button>Run Evaluation</Button>
              </PopoverTrigger>
              <PopoverContent className="w-80 space-y-3">
                <p className="text-sm font-medium">Target agent FQN</p>
                <Input
                  placeholder="finance:kyc"
                  value={agentFqn}
                  onChange={(event) => setAgentFqn(event.target.value)}
                />
                <Button
                  className="w-full"
                  disabled={!agentFqn || runEval.isPending}
                  onClick={async () => {
                    const createdRun = await runEval.mutateAsync({
                      evalSetId,
                      agentFqn,
                    });
                    setSelectedRunId(createdRun.id);
                    void runsQuery.refetch();
                  }}
                >
                  Confirm run
                </Button>
              </PopoverContent>
            </Popover>
            <Button
              disabled={ateConfigsQuery.data?.items.length === 0 && !useAuthStore.getState().user?.roles?.includes("workspace_admin")}
              variant="outline"
              onClick={() => setAdversarialModalOpen(true)}
            >
              Generate Adversarial Tests
            </Button>
          </div>
        </div>
      </div>

      <EvalRunList
        evalSetId={evalSetId}
        isLoading={runsQuery.isLoading}
        onCompare={([runA, runB]) =>
          router.push(
            `/evaluation-testing/compare?runA=${encodeURIComponent(runA)}&runB=${encodeURIComponent(runB)}`,
          )
        }
        onRunSelect={(runId) => {
          setSelectedRunId(runId);
          router.push(
            `/evaluation-testing/${encodeURIComponent(evalSetId)}/runs/${encodeURIComponent(runId)}`,
          );
        }}
        onSelectionChange={setSelectedRunIds}
        runs={runsQuery.data?.items ?? []}
        selectedRunId={selectedRunId}
        selectedRunIds={selectedRunIds}
      />

      {selectedRunIdsArray.length === 2 ? null : null}

      <AdversarialTestReviewModal
        agentFqn={agentFqn}
        evalSetId={evalSetId}
        onClose={() => {
          setAdversarialModalOpen(false);
          void runsQuery.refetch();
        }}
        open={adversarialModalOpen}
        workspaceId={workspaceId}
      />
    </section>
  );
}
