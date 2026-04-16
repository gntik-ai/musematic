"use client";

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, ShieldCheck, ShieldX, Upload } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
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
import { Textarea } from "@/components/ui/textarea";
import { useApproveCertification, useRevokeCertification } from "@/lib/hooks/use-certification-actions";
import { useToast } from "@/lib/hooks/use-toast";
import type { CertificationStatus, ReviewDecisionFormValues } from "@/lib/types/trust-workbench";

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"];

const reviewerFormSchema = z.object({
  decision: z.enum(["approve", "reject"], {
    required_error: "Select a decision.",
  }),
  notes: z.string().trim().min(1, "Review notes are required."),
  supportingFiles: z
    .array(z.instanceof(File))
    .max(5, "You can upload up to 5 files.")
    .refine(
      (files) => files.every((file) => file.size <= MAX_FILE_BYTES),
      "Each file must be 10MB or smaller.",
    )
    .refine(
      (files) =>
        files.every((file) => {
          const lowerName = file.name.toLowerCase();
          return ACCEPTED_EXTENSIONS.some((extension) => lowerName.endsWith(extension));
        }),
      "Only PDF, PNG, and JPG files are allowed.",
    ),
});

export interface ReviewerFormProps {
  certificationId: string;
  agentId: string;
  currentStatus: CertificationStatus;
  isExpired: boolean;
  onDecisionSubmitted: () => void;
}

export function ReviewerForm({
  certificationId,
  currentStatus,
  isExpired,
  onDecisionSubmitted,
}: ReviewerFormProps) {
  const { toast } = useToast();
  const approveMutation = useApproveCertification();
  const revokeMutation = useRevokeCertification();
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);
  const form = useForm<ReviewDecisionFormValues>({
    defaultValues: {
      decision: undefined as unknown as ReviewDecisionFormValues["decision"],
      notes: "",
      supportingFiles: [],
    },
    resolver: zodResolver(reviewerFormSchema),
  });

  const isSubmitting = approveMutation.isPending || revokeMutation.isPending;
  const decisionLabels = isExpired
    ? { approve: "Renew", reject: "Reject" }
    : { approve: "Approve", reject: "Reject" };

  const handleSubmit = form.handleSubmit(async (values) => {
    setConflictMessage(null);

    try {
      if (values.decision === "approve") {
        await approveMutation.mutateAsync({
          certificationId,
          notes: values.notes,
          files: values.supportingFiles,
        });
        toast({
          title: isExpired ? "Certification renewed" : "Certification approved",
          variant: "success",
        });
      } else {
        await revokeMutation.mutateAsync({
          certificationId,
          notes: values.notes,
        });
        toast({
          title: "Certification rejected",
          variant: "success",
        });
      }

      form.reset({
        decision: undefined as unknown as ReviewDecisionFormValues["decision"],
        notes: "",
        supportingFiles: [],
      });
      onDecisionSubmitted();
    } catch (error) {
      if (
        typeof error === "object" &&
        error !== null &&
        "conflictError" in error &&
        (error as { conflictError?: boolean }).conflictError
      ) {
        setConflictMessage("A decision has already been recorded - please refresh");
        return;
      }

      toast({
        title: "Unable to submit the review",
        description:
          error instanceof Error ? error.message : "Try again in a moment.",
        variant: "destructive",
      });
    }
  });

  return (
    <div className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 shadow-sm">
      <div className="mb-5">
        <h3 className="text-lg font-semibold">Reviewer decision</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Record notes and submit the final certification outcome.
        </p>
      </div>

      {currentStatus === "revoked" || currentStatus === "superseded" ? (
        <Alert className="mb-4">
          <AlertTitle>Decision locked</AlertTitle>
          <AlertDescription>
            This certification already has a terminal status and cannot be reviewed again here.
          </AlertDescription>
        </Alert>
      ) : null}

      {conflictMessage ? (
        <Alert className="mb-4" variant="destructive">
          <AlertTitle>Concurrent review detected</AlertTitle>
          <AlertDescription>{conflictMessage}</AlertDescription>
        </Alert>
      ) : null}

      <Form {...form}>
        <form className="space-y-5" onSubmit={handleSubmit}>
          <FormField
            control={form.control}
            name="decision"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Decision</FormLabel>
                <FormControl>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {(["approve", "reject"] as const).map((value) => {
                      const checked = field.value === value;
                      const Icon = value === "approve" ? ShieldCheck : ShieldX;

                      return (
                        <label
                          key={value}
                          className={`flex cursor-pointer items-center gap-3 rounded-2xl border p-4 text-sm transition-colors ${
                            checked
                              ? "border-brand-accent bg-brand-accent/10"
                              : "border-border/60 bg-background/70"
                          }`}
                        >
                          <input
                            checked={checked}
                            className="sr-only"
                            name={field.name}
                            type="radio"
                            value={value}
                            onChange={() => field.onChange(value)}
                          />
                          <Icon className="h-4 w-4 shrink-0 text-brand-accent" />
                          <span>{decisionLabels[value]}</span>
                        </label>
                      );
                    })}
                  </div>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="notes"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Review notes</FormLabel>
                <FormControl>
                  <Textarea
                    {...field}
                    placeholder="Document the rationale behind your decision."
                    rows={6}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="supportingFiles"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Supporting files</FormLabel>
                <FormControl>
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/70 p-4">
                    <label className="inline-flex cursor-pointer items-center gap-2 text-sm font-medium text-foreground">
                      <Upload className="h-4 w-4" />
                      <span>Upload PDF, PNG, or JPG files</span>
                      <input
                        accept=".pdf,.png,.jpg,.jpeg"
                        className="sr-only"
                        multiple
                        type="file"
                        onChange={(event) => {
                          field.onChange(Array.from(event.target.files ?? []));
                        }}
                      />
                    </label>
                    {field.value.length > 0 ? (
                      <ul className="mt-3 space-y-1 text-sm text-muted-foreground">
                        {field.value.map((file) => (
                          <li key={`${file.name}-${file.size}`}>{file.name}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-3 text-sm text-muted-foreground">
                        Optional evidence, up to 5 files and 10MB each.
                      </p>
                    )}
                  </div>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button
            className="w-full"
            disabled={isSubmitting || currentStatus === "revoked" || currentStatus === "superseded"}
            type="submit"
          >
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {fieldLabel(currentStatus, form.watch("decision"), isExpired)}
          </Button>
        </form>
      </Form>
    </div>
  );
}

function fieldLabel(
  currentStatus: CertificationStatus,
  decision: ReviewDecisionFormValues["decision"] | undefined,
  isExpired: boolean,
) {
  if (currentStatus === "revoked" || currentStatus === "superseded") {
    return "Decision recorded";
  }
  if (!decision) {
    return "Submit review";
  }
  if (decision === "approve") {
    return isExpired ? "Renew certification" : "Approve certification";
  }

  return "Reject certification";
}
