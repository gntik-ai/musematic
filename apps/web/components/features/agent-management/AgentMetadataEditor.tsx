"use client";

import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { StaleDataAlert } from "@/components/features/admin/shared/StaleDataAlert";
import { FQNInput } from "@/components/features/agent-management/FQNInput";
import { RoleTypeSelector } from "@/components/features/agent-management/RoleTypeSelector";
import { VisibilityPatternPanel } from "@/components/features/agent-management/VisibilityPatternPanel";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAgent } from "@/lib/hooks/use-agents";
import { useUpdateAgentMetadata } from "@/lib/hooks/use-agent-mutations";
import { useToast } from "@/lib/hooks/use-toast";
import { MetadataFormSchema, type MetadataFormValues } from "@/lib/schemas/agent-management";
import { AGENT_MATURITIES } from "@/lib/types/agent-management";
import { ApiError } from "@/types/api";
import { toTitleCase } from "@/lib/utils";

export interface AgentMetadataEditorProps {
  fqn: string;
  onSaved?: () => void;
}

function toFormValues(agent: NonNullable<ReturnType<typeof useAgent>["data"]>): MetadataFormValues {
  return {
    namespace: agent.namespace,
    local_name: agent.local_name,
    name: agent.name,
    description: agent.description,
    purpose: agent.purpose,
    approach: agent.approach,
    tags: agent.tags,
    category: agent.category,
    maturity_level: agent.maturity_level,
    role_type: agent.role_type,
    custom_role: agent.custom_role,
    reasoning_modes: agent.reasoning_modes,
    visibility_patterns: agent.visibility_patterns,
  };
}

export function AgentMetadataEditor({
  fqn,
  onSaved,
}: AgentMetadataEditorProps) {
  const agentQuery = useAgent(fqn);
  const updateMutation = useUpdateAgentMetadata();
  const { toast } = useToast();
  const [isStale, setIsStale] = useState(false);

  const form = useForm<MetadataFormValues>({
    defaultValues: {
      namespace: "",
      local_name: "",
      name: "",
      description: "",
      purpose: "",
      approach: null,
      tags: [],
      category: "",
      maturity_level: "beta",
      role_type: "executor",
      custom_role: null,
      reasoning_modes: [],
      visibility_patterns: [],
    },
    mode: "onChange",
    resolver: zodResolver(MetadataFormSchema),
  });

  useEffect(() => {
    if (agentQuery.data && !form.formState.isDirty) {
      form.reset(toFormValues(agentQuery.data));
      setIsStale(false);
    }
  }, [agentQuery.data, form, form.formState.isDirty]);

  if (!agentQuery.data) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Metadata editor</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {isStale ? (
          <StaleDataAlert
            onReload={() => {
              void agentQuery.refetch().then((result) => {
                if (result.data) {
                  form.reset(toFormValues(result.data));
                  setIsStale(false);
                }
              });
            }}
          />
        ) : null}
        <Form {...form}>
          <form
            className="space-y-6"
            onSubmit={form.handleSubmit(async (values) => {
              try {
                await updateMutation.mutateAsync({
                  fqn,
                  body: {
                    ...values,
                    tags: values.tags,
                    reasoning_modes: values.reasoning_modes,
                    visibility_patterns: values.visibility_patterns,
                  },
                  lastModified:
                    agentQuery.data?.last_modified ?? agentQuery.data.updated_at,
                });
                toast({
                  title: "Metadata updated",
                  variant: "success",
                });
                onSaved?.();
              } catch (error) {
                if (error instanceof ApiError && error.status === 412) {
                  setIsStale(true);
                  return;
                }

                toast({
                  title: error instanceof ApiError ? error.message : "Unable to save metadata",
                  variant: "destructive",
                });
              }
            })}
          >
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Display name</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FQNInput
              localName={form.watch("local_name")}
              namespace={form.watch("namespace")}
              onLocalNameChange={(value) => form.setValue("local_name", value, { shouldDirty: true, shouldValidate: true })}
              onNamespaceChange={(value) => form.setValue("namespace", value, { shouldDirty: true, shouldValidate: true })}
            />
            {form.formState.errors.namespace || form.formState.errors.local_name ? (
              <div className="grid gap-2 text-sm text-destructive md:grid-cols-[220px_minmax(0,1fr)]">
                <div role="alert">
                  {form.formState.errors.namespace?.message ?? null}
                </div>
                <div role="alert">
                  {form.formState.errors.local_name?.message ?? null}
                </div>
              </div>
            ) : null}
            <div className="grid gap-2 md:grid-cols-2">
              <FormField
                control={form.control}
                name="category"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Category</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="maturity_level"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Maturity</FormLabel>
                    <FormControl>
                      <Select
                        value={field.value}
                        onChange={(event) => field.onChange(event.target.value)}
                      >
                        {AGENT_MATURITIES.map((maturity) => (
                          <option key={maturity} value={maturity}>
                            {toTitleCase(maturity)}
                          </option>
                        ))}
                      </Select>
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
                    <Textarea {...field} rows={4} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="purpose"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Purpose</FormLabel>
                  <FormControl>
                    <Textarea {...field} rows={5} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="approach"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Approach</FormLabel>
                  <FormControl>
                    <Textarea
                      value={field.value ?? ""}
                      onChange={(event) => field.onChange(event.target.value)}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <RoleTypeSelector
              customRole={form.watch("custom_role") ?? ""}
              value={form.watch("role_type")}
              onValueChange={(type, customRole) => {
                form.setValue("role_type", type, { shouldDirty: true });
                form.setValue("custom_role", customRole ?? null, { shouldDirty: true });
              }}
            />

            <VisibilityPatternPanel
              patterns={form.watch("visibility_patterns")}
              onChange={(patterns) =>
                form.setValue("visibility_patterns", patterns, {
                  shouldDirty: true,
                  shouldValidate: true,
                })
              }
            />

            <Alert>
              <AlertTitle>Reasoning modes and tags</AlertTitle>
              <AlertDescription>
                Full tokenized editors for tags and reasoning modes are deferred to the next implementation slice. The API contract and save flow are already wired here.
              </AlertDescription>
            </Alert>

            <div className="flex justify-end">
              <Button disabled={updateMutation.isPending} type="submit">
                {updateMutation.isPending ? "Saving…" : "Save metadata"}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
