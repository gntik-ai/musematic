"use client";

import { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Check, ChevronsUpDown, Search } from "lucide-react";
import { ApiError } from "@/types/api";
import { defaultQuotasSchema, workspaceQuotaOverrideSchema } from "@/lib/schemas/admin";
import {
  useAdminWorkspaces,
  useDefaultQuotas,
  useDefaultQuotasMutation,
  useWorkspaceQuota,
  useWorkspaceQuotaMutation,
} from "@/lib/hooks/use-admin-settings";
import type { DefaultQuotas, WorkspaceQuotaOverride } from "@/lib/types/admin";
import { useToast } from "@/lib/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SettingsFormActions } from "@/components/features/admin/shared/SettingsFormActions";
import { StaleDataAlert } from "@/components/features/admin/shared/StaleDataAlert";

function toDefaultFormValues(data: DefaultQuotas) {
  return {
    max_agents: data.max_agents,
    max_concurrent_executions: data.max_concurrent_executions,
    max_sandboxes: data.max_sandboxes,
    monthly_token_budget: data.monthly_token_budget,
    storage_quota_gb: data.storage_quota_gb,
  };
}

function toOverrideFormValues(data: WorkspaceQuotaOverride) {
  return {
    max_agents: data.max_agents,
    max_concurrent_executions: data.max_concurrent_executions,
    max_sandboxes: data.max_sandboxes,
    monthly_token_budget: data.monthly_token_budget,
    storage_quota_gb: data.storage_quota_gb,
  };
}

const quotaFields: Array<{
  name:
    | "max_agents"
    | "max_concurrent_executions"
    | "max_sandboxes"
    | "monthly_token_budget"
    | "storage_quota_gb";
  label: string;
}> = [
  { name: "max_agents", label: "Max agents" },
  { name: "max_concurrent_executions", label: "Max concurrent executions" },
  { name: "max_sandboxes", label: "Max sandboxes" },
  { name: "monthly_token_budget", label: "Monthly token budget" },
  { name: "storage_quota_gb", label: "Storage quota (GB)" },
];

export function QuotasTab() {
  const defaultQuery = useDefaultQuotas();
  const defaultMutation = useDefaultQuotasMutation();
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [workspaceSearch, setWorkspaceSearch] = useState("");
  const [workspacePickerOpen, setWorkspacePickerOpen] = useState(false);
  const workspaceSearchQuery = useAdminWorkspaces(workspaceSearch);
  const workspaceQuotaQuery = useWorkspaceQuota(selectedWorkspaceId);
  const workspaceQuotaMutation = useWorkspaceQuotaMutation(selectedWorkspaceId);
  const { toast } = useToast();
  const [defaultSaved, setDefaultSaved] = useState(false);
  const [overrideSaved, setOverrideSaved] = useState(false);
  const [defaultStale, setDefaultStale] = useState(false);
  const [overrideStale, setOverrideStale] = useState(false);

  const defaultForm = useForm({
    defaultValues: {
      max_agents: 100,
      max_concurrent_executions: 30,
      max_sandboxes: 12,
      monthly_token_budget: 1000,
      storage_quota_gb: 500,
    },
    resolver: zodResolver(defaultQuotasSchema),
  });

  const overrideForm = useForm({
    defaultValues: {
      max_agents: null,
      max_concurrent_executions: null,
      max_sandboxes: null,
      monthly_token_budget: null,
      storage_quota_gb: null,
    },
    resolver: zodResolver(workspaceQuotaOverrideSchema),
  });

  useEffect(() => {
    if (defaultQuery.data && !defaultForm.formState.isDirty) {
      defaultForm.reset(toDefaultFormValues(defaultQuery.data));
      setDefaultStale(false);
    }
  }, [defaultForm, defaultQuery.data, defaultForm.formState.isDirty]);

  useEffect(() => {
    if (workspaceQuotaQuery.data && !overrideForm.formState.isDirty) {
      overrideForm.reset(toOverrideFormValues(workspaceQuotaQuery.data));
      setOverrideStale(false);
    }
  }, [overrideForm, workspaceQuotaQuery.data, overrideForm.formState.isDirty]);

  const selectedWorkspace = useMemo(
    () =>
      workspaceSearchQuery.data?.items.find(
        (workspace) => workspace.id === selectedWorkspaceId,
      ) ?? null,
    [selectedWorkspaceId, workspaceSearchQuery.data],
  );

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Card>
        <CardHeader>
          <CardTitle>Default quotas</CardTitle>
          <p className="text-sm text-muted-foreground">
            Baseline limits applied to every new workspace.
          </p>
        </CardHeader>
        <CardContent className="space-y-6">
          {defaultStale ? (
            <StaleDataAlert
              onReload={async () => {
                const result = await defaultQuery.refetch();
                if (result.data) {
                  defaultForm.reset(toDefaultFormValues(result.data));
                  setDefaultStale(false);
                }
              }}
            />
          ) : null}
          <Form {...defaultForm}>
            <form
              className="space-y-4"
              onSubmit={defaultForm.handleSubmit(async (values) => {
                if (!defaultQuery.data) {
                  return;
                }

                try {
                  await defaultMutation.mutateAsync({
                    body: values,
                    _version: defaultQuery.data.updated_at,
                  });
                  setDefaultSaved(true);
                } catch (error) {
                  if (error instanceof ApiError && error.status === 412) {
                    setDefaultStale(true);
                    return;
                  }

                  toast({
                    title:
                      error instanceof ApiError
                        ? error.message
                        : "Unable to update default quotas",
                    variant: "destructive",
                  });
                }
              })}
            >
              {quotaFields.map((fieldConfig) => (
                <FormField
                  key={fieldConfig.name}
                  control={defaultForm.control}
                  name={fieldConfig.name}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{fieldConfig.label}</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          {...field}
                          value={field.value}
                          onChange={(event) => field.onChange(event.target.value)}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              ))}

              <SettingsFormActions
                isDirty={defaultForm.formState.isDirty}
                isPending={defaultMutation.isPending}
                isSaved={defaultSaved}
                onClearSaved={() => setDefaultSaved(false)}
                onReset={() => {
                  if (defaultQuery.data) {
                    defaultForm.reset(toDefaultFormValues(defaultQuery.data));
                    setDefaultStale(false);
                  }
                }}
              />
            </form>
          </Form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Workspace overrides</CardTitle>
          <p className="text-sm text-muted-foreground">
            Override any subset of defaults for a specific workspace.
          </p>
        </CardHeader>
        <CardContent className="space-y-6">
          {overrideStale ? (
            <StaleDataAlert
              onReload={async () => {
                const result = await workspaceQuotaQuery.refetch();
                if (result.data) {
                  overrideForm.reset(toOverrideFormValues(result.data));
                  setOverrideStale(false);
                }
              }}
            />
          ) : null}

          <Popover open={workspacePickerOpen} onOpenChange={setWorkspacePickerOpen}>
            <PopoverTrigger asChild>
              <Button
                aria-label="Select workspace override target"
                className="w-full justify-between"
                variant="outline"
              >
                <span className="truncate">
                  {selectedWorkspace?.name ??
                    workspaceQuotaQuery.data?.workspace_name ??
                    "Select workspace"}
                </span>
                <ChevronsUpDown className="h-4 w-4 text-muted-foreground" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[var(--radix-popover-trigger-width,24rem)]">
              <Command>
                <div className="flex items-center gap-2 border-b border-border/70 pb-3">
                  <Search className="h-4 w-4 text-muted-foreground" />
                  <CommandInput
                    aria-label="Search workspaces"
                    placeholder="Search workspaces"
                    value={workspaceSearch}
                    onChange={(event) => setWorkspaceSearch(event.target.value)}
                  />
                </div>
                <CommandList>
                  <CommandEmpty>No workspaces found.</CommandEmpty>
                  <CommandGroup heading="Workspaces">
                    {(workspaceSearchQuery.data?.items ?? []).map((workspace) => (
                      <CommandItem
                        key={workspace.id}
                        onClick={() => {
                          setSelectedWorkspaceId(workspace.id);
                          setWorkspacePickerOpen(false);
                        }}
                      >
                        <span>{workspace.name}</span>
                        {selectedWorkspaceId === workspace.id ? (
                          <Check className="h-4 w-4" />
                        ) : null}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>

          <Form {...overrideForm}>
            <form
              className="space-y-4"
              onSubmit={overrideForm.handleSubmit(async (values) => {
                if (!selectedWorkspaceId || !workspaceQuotaQuery.data) {
                  return;
                }

                try {
                  await workspaceQuotaMutation.mutateAsync({
                    body: values,
                    _version: workspaceQuotaQuery.data.updated_at,
                  });
                  setOverrideSaved(true);
                } catch (error) {
                  if (error instanceof ApiError && error.status === 412) {
                    setOverrideStale(true);
                    return;
                  }

                  toast({
                    title:
                      error instanceof ApiError
                        ? error.message
                        : "Unable to update workspace override",
                    variant: "destructive",
                  });
                }
              })}
            >
              {quotaFields.map((fieldConfig) => (
                <FormField
                  key={fieldConfig.name}
                  control={overrideForm.control}
                  name={fieldConfig.name}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{fieldConfig.label}</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Inherit default"
                          type="number"
                          {...field}
                          disabled={!selectedWorkspaceId}
                          value={field.value ?? ""}
                          onChange={(event) => field.onChange(event.target.value)}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              ))}

              <SettingsFormActions
                disableSave={!selectedWorkspaceId}
                isDirty={overrideForm.formState.isDirty}
                isPending={workspaceQuotaMutation.isPending}
                isSaved={overrideSaved}
                onClearSaved={() => setOverrideSaved(false)}
                onReset={() => {
                  if (workspaceQuotaQuery.data) {
                    overrideForm.reset(toOverrideFormValues(workspaceQuotaQuery.data));
                    setOverrideStale(false);
                  }
                }}
              />
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
