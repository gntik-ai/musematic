"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useRouter } from "next/navigation";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/lib/hooks/use-toast";
import {
  useAgentIdentityMutations,
  type AgentIdentityMutationPayload,
} from "@/lib/hooks/use-agent-identity-mutations";
import {
  AgentFormIdentityFields,
  AgentFormSchema,
  DEFAULT_AGENT_FORM_VALUES,
  type AgentFormValues,
} from "@/components/features/agents/agent-form-identity-fields";
import { AgentFormVisibilityEditor } from "@/components/features/agents/agent-form-visibility-editor";
import { buildAgentFqn } from "@/lib/types/agent-management";

export interface AgentIdentityFormProps {
  mode: "create" | "edit";
  agentId?: string;
  initialValues?: AgentFormValues;
  isLegacy?: boolean;
  title: string;
  description: string;
}

function toPayload(values: AgentFormValues): AgentIdentityMutationPayload {
  return {
    namespace: values.namespace,
    localName: values.localName,
    purpose: values.purpose,
    approach: values.approach,
    roleType: values.roleType,
    visibilityPatterns: values.visibilityPatterns.filter((pattern) => pattern.trim().length > 0),
  };
}

export function AgentIdentityForm({
  mode,
  agentId,
  initialValues,
  isLegacy = false,
  title,
  description,
}: AgentIdentityFormProps) {
  const router = useRouter();
  const { toast } = useToast();
  const { createAgent, updateAgent } = useAgentIdentityMutations(agentId);
  const mutation = mode === "create" ? createAgent : updateAgent;

  const form = useForm<AgentFormValues>({
    defaultValues: initialValues ?? DEFAULT_AGENT_FORM_VALUES,
    mode: "onChange",
    resolver: zodResolver(AgentFormSchema),
  });

  useEffect(() => {
    if (initialValues) {
      form.reset(initialValues);
    }
  }, [form, initialValues]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {mutation.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Unable to save agent identity</AlertTitle>
            <AlertDescription>
              {mutation.error instanceof Error
                ? mutation.error.message
                : "The request could not be completed."}
            </AlertDescription>
          </Alert>
        ) : null}

        <form
          className="space-y-6"
          onSubmit={form.handleSubmit(async (values) => {
            const payload = toPayload(values);
            const response =
              mode === "create"
                ? await createAgent.mutateAsync(payload)
                : await updateAgent.mutateAsync(payload);

            const nextId = encodeURIComponent(
              response.fqn || buildAgentFqn(values.namespace, values.localName),
            );

            toast({
              title: mode === "create" ? "Agent created" : "Agent updated",
              variant: "success",
            });
            router.push(`/agents/${nextId}`);
          })}
        >
          <AgentFormIdentityFields form={form} isLegacy={isLegacy} mode={mode} />
          <AgentFormVisibilityEditor
            value={form.watch("visibilityPatterns")}
            onChange={(patterns) => {
              form.setValue("visibilityPatterns", patterns, {
                shouldDirty: true,
                shouldValidate: true,
              });
            }}
          />

          <div className="flex items-center justify-end gap-3">
            <Button type="button" variant="ghost" onClick={() => router.back()}>
              Cancel
            </Button>
            <Button
              disabled={!form.formState.isValid || mutation.isPending}
              type="submit"
            >
              {mutation.isPending
                ? mode === "create"
                  ? "Creating..."
                  : "Saving..."
                : mode === "create"
                  ? "Create Agent"
                  : "Save Changes"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
