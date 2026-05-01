"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useForm, type Control } from "react-hook-form";
import { z } from "zod";
import { RealLLMOptInDialog } from "@/components/features/shared/RealLLMOptInDialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateScenario,
  useScenario,
  useUpdateScenario,
} from "@/lib/hooks/use-simulation-scenarios";
import type { SimulationScenario, SimulationScenarioInput } from "@/types/simulation";

const secretPattern =
  /(plaintext[_-]?secret|api[_-]?key|secret|token|password)["']?\s*[:=]\s*["']?[A-Za-z0-9_./+=-]{8,}/i;

const scenarioEditorSchema = z.object({
  name: z.string().min(1, "Name is required."),
  description: z.string().optional(),
  agent_fqns: z.string().min(1, "Add at least one agent FQN."),
  workflow_template_id: z.string().optional(),
  mock_set_json: z.string().min(2),
  input_distribution_json: z.string().min(2),
  twin_fidelity_json: z.string().min(2),
  success_criteria_json: z.string().min(2),
  run_schedule_json: z.string().optional(),
});

type ScenarioEditorValues = z.infer<typeof scenarioEditorSchema>;

interface SimulationScenarioEditorProps {
  mode: "create" | "edit";
  workspaceId: string;
  scenarioId?: string | undefined;
  onSaved?: ((scenario: SimulationScenario) => void) | undefined;
}

const defaults: ScenarioEditorValues = {
  name: "",
  description: "",
  agent_fqns: "",
  workflow_template_id: "",
  mock_set_json: '{\n  "llm_provider": "mock-llm"\n}',
  input_distribution_json: '{\n  "type": "fixed",\n  "values": []\n}',
  twin_fidelity_json: '{\n  "subsystems": {}\n}',
  success_criteria_json: '[\n  { "metric": "success_rate", "operator": ">=", "value": 0.95 }\n]',
  run_schedule_json: "",
};

export function SimulationScenarioEditor({
  mode,
  workspaceId,
  scenarioId,
  onSaved,
}: SimulationScenarioEditorProps) {
  const scenarioQuery = useScenario(scenarioId ?? "", workspaceId);
  const createScenario = useCreateScenario();
  const updateScenario = useUpdateScenario(scenarioId ?? "", workspaceId);
  const [formError, setFormError] = useState<string | null>(null);
  const [realLlmPreviewConfirmed, setRealLlmPreviewConfirmed] = useState(false);
  const form = useForm<ScenarioEditorValues>({
    resolver: zodResolver(scenarioEditorSchema),
    defaultValues: defaults,
  });

  useEffect(() => {
    if (mode !== "edit" || !scenarioQuery.data) {
      return;
    }

    form.reset(toEditorValues(scenarioQuery.data));
  }, [form, mode, scenarioQuery.data]);

  const submit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      const payload = toScenarioPayload(values, workspaceId);
      const saved =
        mode === "edit" && scenarioId
          ? await updateScenario.mutateAsync(payload)
          : await createScenario.mutateAsync(payload);
      onSaved?.(saved);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Scenario could not be saved.");
    }
  });

  return (
    <Form {...form}>
      <form className="space-y-6" onSubmit={submit}>
        {formError ? (
          <Alert className="border-destructive/40 bg-destructive/5 text-foreground">
            <AlertTitle>Scenario validation failed</AlertTitle>
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-4 lg:grid-cols-[2fr,1fr]">
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Name</FormLabel>
                <FormControl>
                  <Input placeholder="Regression Scenario A" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="workflow_template_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Workflow template</FormLabel>
                <FormControl>
                  <Input placeholder="Optional workflow UUID" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Textarea placeholder="Operational purpose for this scenario" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="agent_fqns"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Agents</FormLabel>
              <FormControl>
                <Input placeholder="ops:triage, risk:analyst" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <JsonField
            control={form.control}
            label="Mock set"
            name="mock_set_json"
            placeholder='{"llm_provider":"mock-llm"}'
          />
          <JsonField
            control={form.control}
            label="Input distribution"
            name="input_distribution_json"
            placeholder='{"type":"uniform"}'
          />
          <JsonField
            control={form.control}
            label="Twin fidelity"
            name="twin_fidelity_json"
            placeholder='{"subsystems":{"tools":"mock"}}'
          />
          <JsonField
            control={form.control}
            label="Success criteria"
            name="success_criteria_json"
            placeholder='[{"metric":"success_rate","operator":">=","value":0.95}]'
          />
        </div>

        <JsonField
          control={form.control}
          label="Run schedule"
          name="run_schedule_json"
          placeholder='{"cron":"0 8 * * 1"}'
          required={false}
        />

        <div className="flex flex-col gap-3 border-t border-border/70 pt-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-muted-foreground">
            Mock LLM execution is the default. Real LLM preview requires explicit confirmation.
          </div>
          <div className="flex flex-wrap gap-2">
            <RealLLMOptInDialog
              onConfirm={() => setRealLlmPreviewConfirmed(true)}
            />
            {realLlmPreviewConfirmed ? (
              <span className="inline-flex items-center rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs">
                Real LLM preview confirmed
              </span>
            ) : null}
            <Button asChild variant="outline">
              <Link href="/evaluation-testing/simulations/scenarios">Cancel</Link>
            </Button>
            <Button
              disabled={createScenario.isPending || updateScenario.isPending}
              disabledByMaintenance
              type="submit"
            >
              {mode === "edit" ? "Save Scenario" : "Create Scenario"}
            </Button>
          </div>
        </div>
      </form>
    </Form>
  );
}

function JsonField({
  control,
  label,
  name,
  placeholder,
  required = true,
}: {
  control: Control<ScenarioEditorValues>;
  label: string;
  name: keyof ScenarioEditorValues;
  placeholder: string;
  required?: boolean;
}) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Textarea
              className="min-h-32 font-mono text-xs"
              placeholder={placeholder}
              {...field}
              value={field.value ?? ""}
            />
          </FormControl>
          {!required ? (
            <p className="text-xs text-muted-foreground">Leave blank when no schedule applies.</p>
          ) : null}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

function toEditorValues(scenario: SimulationScenario): ScenarioEditorValues {
  return {
    name: scenario.name,
    description: scenario.description ?? "",
    agent_fqns: agentFqnsFromConfig(scenario.agents_config).join(", "),
    workflow_template_id: scenario.workflow_template_id ?? "",
    mock_set_json: JSON.stringify(scenario.mock_set_config, null, 2),
    input_distribution_json: JSON.stringify(scenario.input_distribution, null, 2),
    twin_fidelity_json: JSON.stringify(scenario.twin_fidelity, null, 2),
    success_criteria_json: JSON.stringify(scenario.success_criteria, null, 2),
    run_schedule_json: scenario.run_schedule ? JSON.stringify(scenario.run_schedule, null, 2) : "",
  };
}

function toScenarioPayload(
  values: ScenarioEditorValues,
  workspaceId: string,
): SimulationScenarioInput {
  const agents = values.agent_fqns
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const mockSet = parseJsonObject(values.mock_set_json, "Mock set");
  const inputDistribution = parseJsonObject(values.input_distribution_json, "Input distribution");
  const twinFidelity = parseJsonObject(values.twin_fidelity_json, "Twin fidelity");
  const successCriteria = parseJsonArray(values.success_criteria_json, "Success criteria");
  const runSchedule = values.run_schedule_json?.trim()
    ? parseJsonObject(values.run_schedule_json, "Run schedule")
    : null;

  const secretCandidate = JSON.stringify({
    agents,
    mockSet,
    inputDistribution,
    twinFidelity,
    successCriteria,
    runSchedule,
  });
  if (secretPattern.test(secretCandidate)) {
    throw new Error("Plaintext secrets are not allowed in scenario configuration.");
  }
  if (successCriteria.length === 0) {
    throw new Error("Add at least one success criterion.");
  }

  return {
    workspace_id: workspaceId,
    name: values.name.trim(),
    description: values.description?.trim() || null,
    agents_config: { agents },
    workflow_template_id: values.workflow_template_id?.trim() || null,
    mock_set_config: mockSet,
    input_distribution: inputDistribution,
    twin_fidelity: twinFidelity,
    success_criteria: successCriteria,
    run_schedule: runSchedule,
  };
}

function parseJsonObject(value: string, label: string): Record<string, unknown> {
  const parsed = parseJson(value, label);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function parseJsonArray(value: string, label: string): Array<Record<string, unknown>> {
  const parsed = parseJson(value, label);
  if (!Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON array.`);
  }
  return parsed.filter(
    (item): item is Record<string, unknown> => typeof item === "object" && item !== null,
  );
}

function parseJson(value: string, label: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    throw new Error(`${label} contains invalid JSON.`);
  }
}

function agentFqnsFromConfig(config: Record<string, unknown>): string[] {
  const raw = config.agents ?? config.agent_fqns;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((item) =>
      typeof item === "string"
        ? item
        : typeof item === "object" && item !== null && "fqn" in item
          ? String((item as { fqn: unknown }).fqn)
          : "",
    )
    .filter(Boolean);
}
