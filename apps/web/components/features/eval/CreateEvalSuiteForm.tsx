"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Trash2 } from "lucide-react";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useEvalMutations } from "@/lib/hooks/use-eval-mutations";

const testCaseSchema = z.object({
  input_prompt: z.string().min(1, "Prompt is required."),
  expected_output: z.string().min(1, "Expected output is required."),
});

const createEvalSuiteSchema = z.object({
  name: z.string().min(1, "Name is required.").max(255, "Name is too long."),
  description: z.string().optional(),
  pass_threshold: z.number().min(0).max(1),
  cases: z.array(testCaseSchema).min(1, "Add at least one test case."),
});

type CreateEvalSuiteValues = z.infer<typeof createEvalSuiteSchema>;

export interface CreateEvalSuiteFormProps {
  workspaceId: string;
  onSuccess: (evalSetId: string) => void;
}

export function CreateEvalSuiteForm({
  workspaceId,
  onSuccess,
}: CreateEvalSuiteFormProps) {
  const { addCase, createEvalSet } = useEvalMutations();
  const form = useForm<CreateEvalSuiteValues>({
    resolver: zodResolver(createEvalSuiteSchema),
    defaultValues: {
      name: "",
      description: "",
      pass_threshold: 0.7,
      cases: [{ input_prompt: "", expected_output: "" }],
    },
  });
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "cases",
  });

  const submit = form.handleSubmit(async (values) => {
    const createdEvalSet = await createEvalSet.mutateAsync({
      workspace_id: workspaceId,
      name: values.name,
      description: values.description?.trim() || null,
      pass_threshold: values.pass_threshold,
      scorer_config: {},
    });

    for (const [index, item] of values.cases.entries()) {
      await addCase.mutateAsync({
        evalSetId: createdEvalSet.id,
        payload: {
          input_data: { prompt: item.input_prompt, input_prompt: item.input_prompt },
          expected_output: item.expected_output,
          position: index,
        },
      });
    }

    onSuccess(createdEvalSet.id);
  });

  const errorMessage =
    (createEvalSet.error as Error | null)?.message ??
    (addCase.error as Error | null)?.message ??
    null;

  return (
    <Form {...form}>
      <form className="space-y-6" onSubmit={submit}>
        {errorMessage ? (
          <Alert variant="destructive">
            <AlertTitle>Unable to create eval suite</AlertTitle>
            <AlertDescription>{errorMessage}</AlertDescription>
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
                  <Input placeholder="KYC Agent Quality" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="pass_threshold"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Pass threshold ({Math.round(field.value * 100)}%)</FormLabel>
                <FormControl>
                  <input
                    className="h-10 w-full accent-[hsl(var(--primary))]"
                    max={1}
                    min={0}
                    step={0.05}
                    type="range"
                    value={field.value}
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
                <Textarea placeholder="Optional notes about this suite" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Benchmark cases</h2>
              <p className="text-sm text-muted-foreground">
                Define prompts and expected outputs for this suite.
              </p>
            </div>
            <Button
              variant="secondary"
              onClick={() => append({ input_prompt: "", expected_output: "" })}
            >
              Add Test Case
            </Button>
          </div>

          {fields.map((field, index) => (
            <div
              key={field.id}
              className="grid gap-4 rounded-2xl border border-border/70 bg-card/70 p-4 md:grid-cols-[1fr,1fr,auto]"
            >
              <FormField
                control={form.control}
                name={`cases.${index}.input_prompt`}
                render={({ field: caseField }) => (
                  <FormItem>
                    <FormLabel>Input prompt</FormLabel>
                    <FormControl>
                      <Textarea placeholder="Prompt to evaluate" {...caseField} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name={`cases.${index}.expected_output`}
                render={({ field: caseField }) => (
                  <FormItem>
                    <FormLabel>Expected output</FormLabel>
                    <FormControl>
                      <Textarea placeholder="Expected behavior or answer" {...caseField} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex items-start justify-end">
                <Button
                  aria-label={`Remove test case ${index + 1}`}
                  disabled={fields.length === 1}
                  size="icon"
                  variant="ghost"
                  onClick={() => remove(index)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}

          {form.formState.errors.cases?.message ? (
            <p className="text-sm font-medium text-destructive" role="alert">
              {form.formState.errors.cases.message}
            </p>
          ) : null}
        </div>

        <div className="flex justify-end">
          <Button
            disabled={createEvalSet.isPending || addCase.isPending}
            type="submit"
          >
            Create Eval Suite
          </Button>
        </div>
      </form>
    </Form>
  );
}
