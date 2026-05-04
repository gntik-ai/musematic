"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useStripeCancel, useStripeReactivate } from "@/lib/hooks/use-billing-stripe";

const REASON_OPTIONS = [
  { value: "switched_to_competitor", label: "Switched to a competitor" },
  { value: "too_expensive", label: "Too expensive" },
  { value: "missing_features", label: "Missing features" },
  { value: "other", label: "Other" },
];

interface CancelFormProps {
  workspaceId: string;
  status: string;
  onSuccess?: () => void;
}

export function CancelForm({ workspaceId, status, onSuccess }: CancelFormProps) {
  const [reason, setReason] = useState("");
  const [reasonText, setReasonText] = useState("");
  const cancel = useStripeCancel(workspaceId);
  const reactivate = useStripeReactivate(workspaceId);

  if (status === "cancellation_pending") {
    return (
      <div className="space-y-4">
        <Alert>
          <AlertTitle>Cancellation pending</AlertTitle>
          <AlertDescription>
            Your subscription will end at the period boundary. Reactivate any
            time before to keep Pro features.
          </AlertDescription>
        </Alert>
        <Button
          onClick={() =>
            reactivate.mutate(
              undefined,
              onSuccess ? { onSuccess: () => onSuccess() } : undefined,
            )
          }
          disabled={reactivate.isPending}
        >
          {reactivate.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : null}
          Reactivate subscription
        </Button>
        {reactivate.isError ? (
          <p className="text-sm text-destructive">
            {reactivate.error?.message ?? "Failed."}
          </p>
        ) : null}
      </div>
    );
  }

  const handleCancel = () => {
    if (!reason) return;
    const trimmed = reasonText.trim();
    const payload: { reason: string; reason_text?: string } = { reason };
    if (trimmed) {
      payload.reason_text = trimmed;
    }
    cancel.mutate(
      payload,
      onSuccess ? { onSuccess: () => onSuccess() } : undefined,
    );
  };

  return (
    <div className="space-y-4">
      <Alert variant="destructive">
        <AlertTitle>Cancel subscription</AlertTitle>
        <AlertDescription>
          Your Pro features remain available until the end of the current
          billing period.
        </AlertDescription>
      </Alert>
      <div className="space-y-2">
        <Label htmlFor="cancel-reason">Reason</Label>
        <select
          id="cancel-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        >
          <option value="">Select a reason…</option>
          {REASON_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="cancel-reason-text">Details (optional)</Label>
        <Textarea
          id="cancel-reason-text"
          value={reasonText}
          onChange={(e) => setReasonText(e.target.value)}
          rows={3}
        />
      </div>
      {cancel.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Cancellation failed</AlertTitle>
          <AlertDescription>
            {cancel.error?.message ?? "Unknown error."}
          </AlertDescription>
        </Alert>
      ) : null}
      <Button
        variant="destructive"
        onClick={handleCancel}
        disabled={!reason || cancel.isPending}
      >
        {cancel.isPending ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : null}
        Cancel subscription
      </Button>
    </div>
  );
}
