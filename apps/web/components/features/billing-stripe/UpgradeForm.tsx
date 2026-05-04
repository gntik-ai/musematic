"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useStripeUpgrade } from "@/lib/hooks/use-billing-stripe";

interface UpgradeFormProps {
  workspaceId: string;
  targetPlanSlug: string;
  onSuccess?: (subscriptionId: string) => void;
}

/**
 * UPD-052 — Upgrade form scaffold.
 *
 * The full Stripe Elements integration (`<Elements>` + `<PaymentElement>` + SCA)
 * is wired in a follow-up branch. For now this form accepts a
 * pre-confirmed `pm_*` token — operators or QA scripts can paste a token
 * obtained out-of-band via Stripe's test-mode CLI:
 *
 *     stripe payment_methods create -d type=card \
 *       -d card[token]=tok_visa
 *
 * The token is passed straight to the `/stripe-upgrade` endpoint which
 * attaches it to the customer + creates the subscription. SCA-required
 * cards are NOT supported in this scaffold and will fail with
 * `payment_method_invalid`; the live PaymentElement flow handles SCA
 * end-to-end.
 */
export function UpgradeForm({
  workspaceId,
  targetPlanSlug,
  onSuccess,
}: UpgradeFormProps) {
  const [paymentMethodToken, setPaymentMethodToken] = useState("");
  const upgrade = useStripeUpgrade(workspaceId);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    upgrade.mutate(
      {
        target_plan_slug: targetPlanSlug,
        payment_method_token: paymentMethodToken.trim(),
      },
      {
        onSuccess: (response) => {
          onSuccess?.(response.subscription_id);
        },
      },
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Alert>
        <AlertTitle>Test-mode card flow</AlertTitle>
        <AlertDescription>
          Paste a Stripe test payment-method token (`pm_*`). Live SCA flow
          ships in the follow-up branch via the embedded PaymentElement.
        </AlertDescription>
      </Alert>
      <div className="space-y-2">
        <Label htmlFor="payment-method-token">Payment method token</Label>
        <Input
          id="payment-method-token"
          value={paymentMethodToken}
          onChange={(e) => setPaymentMethodToken(e.target.value)}
          placeholder="pm_..."
          autoComplete="off"
          required
        />
      </div>
      {upgrade.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Upgrade failed</AlertTitle>
          <AlertDescription>
            {upgrade.error?.message ?? "Unknown error."}
          </AlertDescription>
        </Alert>
      ) : null}
      <Button
        type="submit"
        disabled={upgrade.isPending || paymentMethodToken.trim().length === 0}
      >
        {upgrade.isPending ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : null}
        Upgrade to {targetPlanSlug}
      </Button>
    </form>
  );
}
