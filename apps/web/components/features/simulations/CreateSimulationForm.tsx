"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useDigitalTwins } from "@/lib/hooks/use-digital-twins";
import { useIsolationPolicies } from "@/lib/hooks/use-isolation-policies";
import { useSimulationMutations } from "@/lib/hooks/use-simulation-mutations";

const scenarioFieldSchema = z.object({
  key: z.string().min(1, "Key is required."),
  value: z.string().min(1, "Value is required."),
});

const createSimulationSchema = z.object({
  name: z.string().min(1, "Name is required."),
  description: z.string().optional(),
  digital_twin_ids: z.array(z.string()).min(1, "Select at least one digital twin."),
  isolation_policy_id: z.string().optional(),
  duration_seconds: z
    .number()
    .positive("Duration must be positive.")
    .optional()
    .or(z.nan().optional()),
  scenario_fields: z.array(scenarioFieldSchema),
});

type CreateSimulationValues = z.infer<typeof createSimulationSchema>;

export interface CreateSimulationFormProps {
  workspaceId: string;
  onSuccess: (runId: string) => void;
}

export function CreateSimulationForm({
  workspaceId,
  onSuccess,
}: CreateSimulationFormProps) {
  const digitalTwinsQuery = useDigitalTwins(workspaceId, true);
  const isolationPoliciesQuery = useIsolationPolicies(workspaceId);
  const { createRun } = useSimulationMutations();
  const [pickerOpen, setPickerOpen] = useState(false);
  const form = useForm<CreateSimulationValues>({
    resolver: zodResolver(createSimulationSchema),
    defaultValues: {
      name: "",
      description: "",
      digital_twin_ids: [],
      isolation_policy_id: "",
      duration_seconds: undefined,
      scenario_fields: [],
    },
  });
  const scenarioFields = useFieldArray({
    control: form.control,
    name: "scenario_fields",
  });
  const selectedTwinIds = form.watch("digital_twin_ids");

  useEffect(() => {
    const defaultPolicy = isolationPoliciesQuery.data?.items.find(
      (policy) => policy.is_default,
    );
    if (defaultPolicy && !form.getValues("isolation_policy_id")) {
      form.setValue("isolation_policy_id", defaultPolicy.policy_id);
    }
  }, [form, isolationPoliciesQuery.data]);

  const selectedTwins = useMemo(
    () =>
      (digitalTwinsQuery.data?.items ?? []).filter((twin) =>
        selectedTwinIds.includes(twin.twin_id),
      ),
    [digitalTwinsQuery.data, selectedTwinIds],
  );
  const twinsWithWarnings = selectedTwins.filter(
    (twin) => twin.warning_flags.length > 0,
  );

  const submit = form.handleSubmit(async (values) => {
    const scenarioConfig: Record<string, unknown> = {};
    if (typeof values.duration_seconds === "number" && Number.isFinite(values.duration_seconds)) {
      scenarioConfig.duration_seconds = values.duration_seconds;
    }
    values.scenario_fields.forEach((field) => {
      scenarioConfig[field.key] = field.value;
    });

    const createdRun = await createRun.mutateAsync({
      workspace_id: workspaceId,
      name: values.name,
      description: values.description?.trim() || null,
      digital_twin_ids: values.digital_twin_ids,
      isolation_policy_id: values.isolation_policy_id || null,
      scenario_config: scenarioConfig,
    });
    onSuccess(createdRun.run_id);
  });

  return (
    <Form {...form}>
      <form className="space-y-6" onSubmit={submit}>
        {twinsWithWarnings.length > 0 ? (
          <Alert className="border-amber-500/30 bg-amber-500/10 text-foreground">
            <AlertTitle>Selected twins need attention</AlertTitle>
            <AlertDescription>
              {twinsWithWarnings.map((twin) => (
                <span className="block" key={twin.twin_id}>
                  {twin.source_agent_fqn}: {twin.warning_flags.join(", ")}
                </span>
              ))}
            </AlertDescription>
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
                  <Input placeholder="KYC Load Test" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="duration_seconds"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Duration (seconds)</FormLabel>
                <FormControl>
                  <Input
                    min={1}
                    type="number"
                    value={typeof field.value === "number" ? field.value : ""}
                    onChange={(event) => field.onChange(Number(event.target.value))}
                  />
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
                <Textarea placeholder="Optional notes for this simulation" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="digital_twin_ids"
          render={() => (
            <FormItem>
              <FormLabel>Digital twins</FormLabel>
              <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
                <PopoverTrigger asChild>
                  <Button className="justify-start" variant="outline">
                    {selectedTwins.length > 0
                      ? `${selectedTwins.length} twin${selectedTwins.length === 1 ? "" : "s"} selected`
                      : "Select digital twins"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[min(90vw,28rem)] p-0">
                  <Command>
                    <CommandInput placeholder="Search twins" />
                    <CommandList>
                      <CommandEmpty>No digital twins found.</CommandEmpty>
                      <CommandGroup heading="Active twins">
                        {(digitalTwinsQuery.data?.items ?? []).map((twin) => {
                          const selected = selectedTwinIds.includes(twin.twin_id);
                          return (
                            <CommandItem
                              key={twin.twin_id}
                              onClick={() => {
                                const next = selected
                                  ? selectedTwinIds.filter((id) => id !== twin.twin_id)
                                  : [...selectedTwinIds, twin.twin_id];
                                form.setValue("digital_twin_ids", next, {
                                  shouldValidate: true,
                                });
                              }}
                            >
                              <div className="space-y-1 text-left">
                                <div className="font-medium">
                                  {twin.source_agent_fqn} v{twin.version}
                                </div>
                                <div className="flex flex-wrap gap-1">
                                  {twin.warning_flags.map((flag) => (
                                    <Badge
                                      className="border-amber-500/30 bg-amber-500/10 text-foreground"
                                      key={flag}
                                      variant="outline"
                                    >
                                      {flag}
                                    </Badge>
                                  ))}
                                </div>
                              </div>
                              <span>{selected ? "Selected" : ""}</span>
                            </CommandItem>
                          );
                        })}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="isolation_policy_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Isolation policy</FormLabel>
              <FormControl>
                <Select {...field}>
                  <option value="">No isolation policy</option>
                  {(isolationPoliciesQuery.data?.items ?? []).map((policy) => (
                    <option key={policy.policy_id} value={policy.policy_id}>
                      {policy.name}
                    </option>
                  ))}
                </Select>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Scenario config</h2>
              <p className="text-sm text-muted-foreground">
                Add optional key-value overrides for this simulation scenario.
              </p>
            </div>
            <Button
              variant="secondary"
              onClick={() => scenarioFields.append({ key: "", value: "" })}
            >
              Add field
            </Button>
          </div>
          {scenarioFields.fields.map((field, index) => (
            <div
              className="grid gap-3 rounded-2xl border border-border/70 bg-card/70 p-4 md:grid-cols-[1fr,1fr,auto]"
              key={field.id}
            >
              <FormField
                control={form.control}
                name={`scenario_fields.${index}.key`}
                render={({ field: itemField }) => (
                  <FormItem>
                    <FormLabel>Key</FormLabel>
                    <FormControl>
                      <Input placeholder="temperature" {...itemField} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name={`scenario_fields.${index}.value`}
                render={({ field: itemField }) => (
                  <FormItem>
                    <FormLabel>Value</FormLabel>
                    <FormControl>
                      <Input placeholder="0.2" {...itemField} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex items-start justify-end">
                <Button
                  aria-label={`Remove scenario field ${index + 1}`}
                  size="icon"
                  variant="ghost"
                  onClick={() => scenarioFields.remove(index)}
                >
                  ×
                </Button>
              </div>
            </div>
          ))}
        </div>

        <div className="flex justify-end">
          <Button disabled={createRun.isPending} disabledByMaintenance type="submit">
            Launch Simulation
          </Button>
        </div>
      </form>
    </Form>
  );
}
