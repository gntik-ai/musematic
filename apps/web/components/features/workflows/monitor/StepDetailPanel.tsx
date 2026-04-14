"use client";

import { useEffect, useRef, useState } from "react";
import { Check, X, XCircle } from "lucide-react";
import { ReasoningTraceViewer } from "@/components/features/workflows/monitor/ReasoningTraceViewer";
import { SelfCorrectionChart } from "@/components/features/workflows/monitor/SelfCorrectionChart";
import { StepOverviewTab } from "@/components/features/workflows/monitor/StepOverviewTab";
import { TaskPlanViewer } from "@/components/features/workflows/monitor/TaskPlanViewer";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useApprovalDecision } from "@/lib/hooks/use-execution-controls";
import { useReasoningTrace } from "@/lib/hooks/use-reasoning-trace";
import { useStepDetail } from "@/lib/hooks/use-step-detail";
import { useTaskPlan } from "@/lib/hooks/use-task-plan";
import {
  useExecutionMonitorStore,
  type ExecutionMonitorDetailTab,
} from "@/lib/stores/execution-monitor-store";

const tabDefinitions: Array<{
  id: ExecutionMonitorDetailTab;
  label: string;
}> = [
  { id: "overview", label: "Overview" },
  { id: "reasoning", label: "Reasoning Trace" },
  { id: "self-correction", label: "Self-Correction" },
  { id: "task-plan", label: "Task Plan" },
];

export function StepDetailPanel({
  executionId,
}: {
  executionId: string;
}) {
  const selectedStepId = useExecutionMonitorStore((state) => state.selectedStepId);
  const activeDetailTab = useExecutionMonitorStore((state) => state.activeDetailTab);
  const setDetailTab = useExecutionMonitorStore((state) => state.setDetailTab);
  const selectStep = useExecutionMonitorStore((state) => state.selectStep);
  const stepStatuses = useExecutionMonitorStore((state) => state.stepStatuses);
  const [approvalComment, setApprovalComment] = useState("");
  const [selectedIterationNumber, setSelectedIterationNumber] = useState<number | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);

  const stepDetailQuery = useStepDetail(executionId, selectedStepId);
  const reasoningTraceQuery = useReasoningTrace(executionId, selectedStepId);
  const taskPlanQuery = useTaskPlan(
    executionId,
    selectedStepId,
    activeDetailTab === "task-plan",
  );
  const approvalDecision = useApprovalDecision(executionId);

  useEffect(() => {
    if (!selectedStepId) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        selectStep(null);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [selectStep, selectedStepId]);

  useEffect(() => {
    setApprovalComment("");
  }, [selectedStepId]);

  useEffect(() => {
    if (!selectedStepId) {
      return;
    }

    panelRef.current?.focus();
  }, [selectedStepId]);

  if (!selectedStepId) {
    return null;
  }

  const currentStepStatus = stepStatuses[selectedStepId] ?? stepDetailQuery.data?.status;

  return (
    <aside
      aria-label={`Step detail for ${selectedStepId}`}
      className="w-full rounded-3xl border border-border/70 bg-background/95 p-5 shadow-2xl"
      data-step-id={selectedStepId}
      ref={panelRef}
      tabIndex={-1}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Step detail
          </p>
          <h2 className="text-2xl font-semibold text-foreground">
            {selectedStepId}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Inspect execution output, reasoning, self-correction, and task planning artifacts.
          </p>
        </div>
        <Button
          aria-label="Close step detail"
          onClick={() => {
            selectStep(null);
          }}
          size="icon"
          variant="ghost"
        >
          <XCircle className="h-5 w-5" />
        </Button>
      </div>

      <Tabs className="mt-6">
        <TabsList className="flex w-full flex-wrap gap-2 bg-transparent p-0">
          {tabDefinitions.map((tab) => (
            <TabsTrigger
              className={cn(
                "border border-border/60 bg-background text-muted-foreground",
                activeDetailTab === tab.id &&
                  "bg-brand-primary/10 text-foreground",
              )}
              key={tab.id}
              onClick={() => {
                setDetailTab(tab.id);
              }}
            >
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent>
          {activeDetailTab === "overview" ? (
            <div className="space-y-4">
              {currentStepStatus === "waiting_for_approval" ? (
                <Alert>
                  <AlertTitle>Approval required</AlertTitle>
                  <AlertDescription>
                    This step is waiting for an operator decision before the workflow can continue.
                  </AlertDescription>
                </Alert>
              ) : null}

              <StepOverviewTab
                isLoading={stepDetailQuery.isLoading}
                stepDetail={stepDetailQuery.data}
              />

              {currentStepStatus === "waiting_for_approval" ? (
                <div className="space-y-3 rounded-2xl border border-border/70 bg-card/80 p-4">
                  <div>
                    <h3 className="font-semibold text-foreground">
                      Approval decision
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      Add an optional comment before approving or rejecting the step.
                    </p>
                  </div>
                  <Textarea
                    onChange={(event) => {
                      setApprovalComment(event.target.value);
                    }}
                    placeholder="Optional approval comment"
                    value={approvalComment}
                  />
                  <div className="flex flex-wrap gap-3">
                    <Button
                      disabled={approvalDecision.isPending}
                      onClick={async () => {
                        await approvalDecision.mutateAsync({
                          stepId: selectedStepId,
                          decision: "approved",
                          comment: approvalComment || undefined,
                        });
                        setApprovalComment("");
                      }}
                    >
                      <Check className="h-4 w-4" />
                      Approve
                    </Button>
                    <Button
                      disabled={approvalDecision.isPending}
                      onClick={async () => {
                        await approvalDecision.mutateAsync({
                          stepId: selectedStepId,
                          decision: "rejected",
                          comment: approvalComment || undefined,
                        });
                        setApprovalComment("");
                      }}
                      variant="destructive"
                    >
                      <X className="h-4 w-4" />
                      Reject
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {activeDetailTab === "reasoning" ? (
            <ReasoningTraceViewer
              isLoading={reasoningTraceQuery.isLoading}
              reasoningTrace={reasoningTraceQuery.reasoningTrace}
            />
          ) : null}

          {activeDetailTab === "self-correction" ? (
            <SelfCorrectionChart
              isLoading={reasoningTraceQuery.isLoading}
              loop={reasoningTraceQuery.selfCorrectionLoop}
              onSelectIteration={setSelectedIterationNumber}
              selectedIterationNumber={selectedIterationNumber}
            />
          ) : null}

          {activeDetailTab === "task-plan" ? (
            <TaskPlanViewer
              isLoading={taskPlanQuery.isLoading}
              taskPlan={taskPlanQuery.data}
            />
          ) : null}
        </TabsContent>
      </Tabs>
    </aside>
  );
}
