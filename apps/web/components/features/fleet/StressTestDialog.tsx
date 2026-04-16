"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { Select } from "@/components/ui/select";
import { useCancelStressTest, useStressTestProgress, useTriggerStressTest } from "@/lib/hooks/use-stress-test";

interface StressTestDialogProps {
  fleetId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRunStateChange?: (isRunning: boolean) => void;
}

const durationOptions = [
  { label: "5 min", value: 5 },
  { label: "15 min", value: 15 },
  { label: "30 min", value: 30 },
  { label: "1 hour", value: 60 },
];

export function StressTestDialog({
  fleetId,
  open,
  onOpenChange,
  onRunStateChange,
}: StressTestDialogProps) {
  const [durationMinutes, setDurationMinutes] = useState(15);
  const [loadLevel, setLoadLevel] = useState<"low" | "medium" | "high">("medium");
  const [runId, setRunId] = useState<string | null>(null);
  const triggerStressTestMutation = useTriggerStressTest();
  const cancelStressTestMutation = useCancelStressTest();
  const progressQuery = useStressTestProgress(runId);

  useEffect(() => {
    const status = progressQuery.data?.status;
    const isRunning = status === "provisioning" || status === "running";
    onRunStateChange?.(isRunning);
  }, [onRunStateChange, progressQuery.data?.status]);

  const progressValue = useMemo(() => {
    const progress = progressQuery.data;
    if (!progress || progress.total_seconds === 0) {
      return 0;
    }

    return Math.round((progress.elapsed_seconds / progress.total_seconds) * 100);
  }, [progressQuery.data]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl space-y-5">
        <DialogHeader>
          <DialogTitle>Stress test</DialogTitle>
          <DialogDescription>
            Launch a synthetic load run against the fleet and track live execution metrics.
          </DialogDescription>
        </DialogHeader>

        {!runId ? (
          <>
            <div className="space-y-2">
              <label className="block text-sm font-medium" htmlFor="stress-duration">
                Duration
              </label>
              <Select
                id="stress-duration"
                value={String(durationMinutes)}
                onChange={(event) => setDurationMinutes(Number(event.target.value))}
              >
                {durationOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium" htmlFor="stress-load">
                Load level
              </label>
              <Select
                id="stress-load"
                value={loadLevel}
                onChange={(event) => setLoadLevel(event.target.value as "low" | "medium" | "high")}
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </Select>
            </div>

            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                disabled={triggerStressTestMutation.isPending}
                onClick={() => {
                  void triggerStressTestMutation
                    .mutateAsync({ fleetId, durationMinutes, loadLevel })
                    .then((response) => setRunId(response.simulation_run_id));
                }}
              >
                Start test
              </Button>
            </DialogFooter>
          </>
        ) : (
          <div className="space-y-5">
            <div className="space-y-3 rounded-3xl border border-border/60 bg-card/70 p-5">
              <Progress value={progressValue} />
              <div className="grid gap-3 text-sm sm:grid-cols-2">
                <p>Elapsed: {progressQuery.data?.elapsed_seconds ?? 0}s</p>
                <p>Total: {progressQuery.data?.total_seconds ?? 0}s</p>
                <p>Executions: {progressQuery.data?.simulated_executions ?? 0}</p>
                <p>
                  Success rate: {Math.round((progressQuery.data?.current_success_rate ?? 0) * 100)}%
                </p>
                <p>
                  Avg latency: {Math.round(progressQuery.data?.current_avg_latency_ms ?? 0)}ms
                </p>
                <p className="capitalize">Status: {progressQuery.data?.status ?? "provisioning"}</p>
              </div>
            </div>

            <DialogFooter>
              <Button
                variant="ghost"
                onClick={() => {
                  setRunId(null);
                  onOpenChange(false);
                }}
              >
                Close
              </Button>
              <Button
                disabled={!runId || cancelStressTestMutation.isPending}
                variant="destructive"
                onClick={() => {
                  if (!runId) {
                    return;
                  }

                  void cancelStressTestMutation.mutateAsync({ runId });
                }}
              >
                Cancel test
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

