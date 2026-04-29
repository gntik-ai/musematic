"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AdversarialTestReviewModal } from "@/components/features/eval/AdversarialTestReviewModal";
import { EvalRunList } from "@/components/features/eval/EvalRunList";
import { TagLabelFilterToolbar } from "@/components/features/tagging/TagLabelFilterToolbar";
import { CalibrationBoxplot } from "@/components/features/evaluation/calibration-boxplot";
import { RubricEditor } from "@/components/features/evaluation/rubric-editor";
import { TrajectoryComparisonSelector } from "@/components/features/evaluation/trajectory-comparison-selector";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useEvalMutations } from "@/lib/hooks/use-eval-mutations";
import { useEvalRuns } from "@/lib/hooks/use-eval-runs";
import { useEvalSet } from "@/lib/hooks/use-eval-sets";
import { useRubricEditor } from "@/lib/hooks/use-rubric-editor";
import { useAteConfigs } from "@/lib/hooks/use-ate";
import {
  parseTagLabelFilters,
  savedViewFiltersToSearchParams,
  writeTagLabelFilters,
} from "@/lib/tagging/filter-query";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";
import type { TrajectoryComparisonMethod } from "@/types/evaluation";

const SECTIONS = ["rubric", "calibration", "comparison"] as const;
type SuiteSection = (typeof SECTIONS)[number];

function resolveSection(value: string | null): SuiteSection {
  return SECTIONS.includes(value as SuiteSection) ? (value as SuiteSection) : "rubric";
}

interface EvalSuiteDetailPageProps {
  params: Promise<{ evalSetId: string }>;
}

export default function EvalSuiteDetailPage({ params }: EvalSuiteDetailPageProps) {
  const { evalSetId } = use(params);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const tagLabelFilters = useMemo(
    () => parseTagLabelFilters(searchParams),
    [searchParams],
  );
  const evalSetQuery = useEvalSet(evalSetId);
  const runsQuery = useEvalRuns(workspaceId ?? "", evalSetId, tagLabelFilters);
  const ateConfigsQuery = useAteConfigs(workspaceId ?? "");
  const { runEval } = useEvalMutations();
  const { rubric, saveRubric } = useRubricEditor(evalSetId);
  const [selectedRunId, setSelectedRunId] = useState<string | undefined>(undefined);
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  const [agentFqn, setAgentFqn] = useState("");
  const [adversarialModalOpen, setAdversarialModalOpen] = useState(false);
  const [comparisonMethod, setComparisonMethod] = useState<TrajectoryComparisonMethod>("exact_match");
  const activeSection = useMemo(() => resolveSection(searchParams.get("section")), [searchParams]);

  useEffect(() => {
    if (runsQuery.data?.items[0]?.agent_fqn && !agentFqn) {
      setAgentFqn(runsQuery.data.items[0].agent_fqn);
    }
  }, [agentFqn, runsQuery.data]);

  useEffect(() => {
    if (rubric?.comparisonMethod) {
      setComparisonMethod(rubric.comparisonMethod);
    }
  }, [rubric?.comparisonMethod]);

  const selectedSuite = evalSetQuery.data;
  const setSection = (section: SuiteSection) => {
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set("section", section);
    router.replace(`${pathname}?${nextParams.toString()}`);
  };

  const replaceSearchParams = (nextParams: URLSearchParams) => {
    const nextQuery = nextParams.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname);
  };

  if (!workspaceId) {
    return <EmptyState description="Select a workspace before browsing suite details." title="Workspace required" />;
  }

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <Link className="text-sm text-muted-foreground underline-offset-4 hover:underline" href="/evaluation-testing">
          Back to Eval Suites
        </Link>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight">{selectedSuite?.name ?? "Eval Suite Detail"}</h1>
            <p className="max-w-3xl text-sm text-muted-foreground">
              {selectedSuite?.description ?? "Benchmark run history and verdict drill-down for this suite."}
            </p>
            <p className="text-sm text-muted-foreground">
              Pass threshold: {typeof selectedSuite?.pass_threshold === "number" ? `${Math.round(selectedSuite.pass_threshold * 100)}%` : "—"}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Popover>
              <PopoverTrigger asChild>
                <Button>Run Evaluation</Button>
              </PopoverTrigger>
              <PopoverContent className="w-80 space-y-3">
                <p className="text-sm font-medium">Target agent FQN</p>
                <Input placeholder="finance:kyc" value={agentFqn} onChange={(event) => setAgentFqn(event.target.value)} />
                <Button
                  className="w-full"
                  disabled={!agentFqn || runEval.isPending}
                  onClick={async () => {
                    const createdRun = await runEval.mutateAsync({ evalSetId, agentFqn });
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

      <TagLabelFilterToolbar
        entityType="evaluation_run"
        savedViewFilters={{ ...tagLabelFilters, eval_set_id: evalSetId }}
        value={tagLabelFilters}
        workspaceId={workspaceId}
        onApplySavedView={(savedFilters) =>
          replaceSearchParams(
            savedViewFiltersToSearchParams(searchParams, savedFilters, ["cursor"]),
          )
        }
        onChange={(nextFilters) =>
          replaceSearchParams(writeTagLabelFilters(searchParams, nextFilters))
        }
      />

      <EvalRunList
        evalSetId={evalSetId}
        isLoading={runsQuery.isLoading}
        onCompare={([runA, runB]) =>
          router.push(`/evaluation-testing/compare?runA=${encodeURIComponent(runA)}&runB=${encodeURIComponent(runB)}`)
        }
        onRunSelect={(runId) => {
          setSelectedRunId(runId);
          router.push(`/evaluation-testing/${encodeURIComponent(evalSetId)}/runs/${encodeURIComponent(runId)}`);
        }}
        onSelectionChange={setSelectedRunIds}
        runs={runsQuery.data?.items ?? []}
        selectedRunId={selectedRunId}
        selectedRunIds={selectedRunIds}
      />

      <Card>
        <CardHeader>
          <CardTitle>Evaluation suite configuration</CardTitle>
          <CardDescription>
            Tune rubric dimensions, review calibration spread, and change the trajectory comparison strategy.
          </CardDescription>
          <div className="flex flex-wrap gap-2">
            {SECTIONS.map((section) => (
              <Button key={section} variant={activeSection === section ? "default" : "outline"} onClick={() => setSection(section)}>
                {section.charAt(0).toUpperCase() + section.slice(1)}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {activeSection === "rubric" ? <RubricEditor suiteId={evalSetId} /> : null}
          {activeSection === "calibration" ? <CalibrationBoxplot suiteId={evalSetId} /> : null}
          {activeSection === "comparison" ? (
            <Card>
              <CardHeader>
                <CardTitle>Trajectory comparison</CardTitle>
                <CardDescription>
                  Pick the method used when this suite compares execution trajectories.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <TrajectoryComparisonSelector value={comparisonMethod} onChange={setComparisonMethod} />
                <div className="flex justify-end">
                  <Button
                    disabled={!rubric || saveRubric.isPending}
                    onClick={() => {
                      if (!rubric) {
                        return;
                      }
                      void saveRubric.mutateAsync({
                        name: rubric.name,
                        description: rubric.description,
                        dimensions: rubric.dimensions,
                        comparisonMethod,
                      });
                    }}
                  >
                    Save comparison
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </CardContent>
      </Card>

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
