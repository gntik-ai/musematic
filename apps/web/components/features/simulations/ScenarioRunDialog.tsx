"use client";

import { useState } from "react";
import { RealLLMOptInDialog } from "@/components/features/shared/RealLLMOptInDialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useRunScenario } from "@/lib/hooks/use-simulation-scenarios";
import type { ScenarioRunSummary, SimulationScenario } from "@/types/simulation";

export interface ScenarioRunDialogProps {
  open: boolean;
  scenario: SimulationScenario | null;
  workspaceId: string;
  workspaceIterationCap?: number;
  onOpenChange: (open: boolean) => void;
  onQueued: (summary: ScenarioRunSummary) => void;
}

export function ScenarioRunDialog({
  open,
  scenario,
  workspaceId,
  workspaceIterationCap = 25,
  onOpenChange,
  onQueued,
}: ScenarioRunDialogProps) {
  const [iterations, setIterations] = useState(1);
  const [useRealLlm, setUseRealLlm] = useState(false);
  const [realLlmConfirmed, setRealLlmConfirmed] = useState(false);
  const runScenario = useRunScenario(scenario?.id ?? "", workspaceId);
  const exceedsCap = iterations > workspaceIterationCap;
  const canSubmit = Boolean(scenario && iterations > 0 && !exceedsCap && (!useRealLlm || realLlmConfirmed));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Launch scenario</DialogTitle>
          <DialogDescription>
            {scenario ? `Queue runs for ${scenario.name}.` : "Select a scenario to launch."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-5">
          <label className="grid gap-2 text-sm font-medium">
            <span>Iterations</span>
            <Input
              min={1}
              type="number"
              value={iterations}
              onChange={(event) => setIterations(Number(event.target.value))}
            />
          </label>
          {exceedsCap ? (
            <p className="text-sm text-destructive">
              Workspace cap is {workspaceIterationCap} iterations per launch.
            </p>
          ) : null}
          <label className="flex items-center justify-between gap-4 rounded-lg border border-border/70 p-3 text-sm">
            <span>Use real LLM</span>
            <Switch
              checked={useRealLlm}
              onCheckedChange={(checked) => {
                setUseRealLlm(checked);
                setRealLlmConfirmed(false);
              }}
            />
          </label>
          {useRealLlm ? (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
              <RealLLMOptInDialog onConfirm={() => setRealLlmConfirmed(true)} />
              {realLlmConfirmed ? (
                <p className="mt-2 text-xs text-muted-foreground">Real LLM execution confirmed.</p>
              ) : null}
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!canSubmit || runScenario.isPending}
            disabledByMaintenance
            onClick={async () => {
              if (!scenario) {
                return;
              }
              const summary = await runScenario.mutateAsync({
                iterations,
                use_real_llm: useRealLlm,
                confirmation_token: useRealLlm ? "USE_REAL_LLM" : null,
              });
              onQueued(summary);
              onOpenChange(false);
            }}
          >
            Queue Runs
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
