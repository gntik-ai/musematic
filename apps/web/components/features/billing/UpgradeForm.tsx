"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CreditCard } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { useUpgradeSubscription } from "@/lib/hooks/use-plan-mutations";
import { useWorkspaceBilling } from "@/lib/hooks/use-workspace-billing";

const upgradeSchema = z.object({
  payment_method_token: z.string().min(1, "Payment token is required").max(256),
});

export function UpgradeForm({ workspaceId }: { workspaceId: string }) {
  const billing = useWorkspaceBilling(workspaceId);
  const upgrade = useUpgradeSubscription(workspaceId);
  const form = useForm<z.infer<typeof upgradeSchema>>({
    resolver: zodResolver(upgradeSchema),
    defaultValues: { payment_method_token: "stub_pm_test" },
  });
  const upgradePreview = upgrade.data?.preview;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upgrade plan</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 text-sm sm:grid-cols-3">
          <div>
            <div className="text-muted-foreground">Current plan</div>
            <div className="font-medium">{billing.data?.subscription.plan_slug ?? "free"}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Target plan</div>
            <div className="font-medium">pro</div>
          </div>
          <div>
            <div className="text-muted-foreground">Proration</div>
            <div className="font-medium">
              EUR {upgradePreview?.prorated_charge_eur ?? "0.00"}
            </div>
          </div>
        </div>
        <Form {...form}>
          <form
            className="space-y-4"
            onSubmit={form.handleSubmit((values) =>
              upgrade.mutate({
                workspaceId,
                target_plan_slug: "pro",
                payment_method_token: values.payment_method_token,
              }),
            )}
          >
            <FormField
              control={form.control}
              name="payment_method_token"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Payment method token</FormLabel>
                  <FormControl>
                    <Input autoComplete="off" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" disabled={upgrade.isPending}>
              <CreditCard className="h-4 w-4" />
              Confirm upgrade
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
