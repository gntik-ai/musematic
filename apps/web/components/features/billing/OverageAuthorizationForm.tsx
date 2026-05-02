"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { useAuthorizeOverage, useRevokeOverage } from "@/lib/hooks/use-overage-authorize";
import { useOverageAuthorization, useWorkspaceBilling } from "@/lib/hooks/use-workspace-billing";

const schema = z.object({
  max_overage_eur: z.string().optional(),
});

interface OverageAuthorizationFormProps {
  workspaceId: string;
}

export function OverageAuthorizationForm({ workspaceId }: OverageAuthorizationFormProps) {
  const billing = useWorkspaceBilling(workspaceId);
  const overage = useOverageAuthorization(workspaceId);
  const authorize = useAuthorizeOverage(workspaceId);
  const revoke = useRevokeOverage(workspaceId);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { max_overage_eur: "" },
  });

  const state = overage.data ?? billing.data?.overage;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Overage authorization</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {state ? (
          <div className="grid gap-3 text-sm sm:grid-cols-3">
            <div>
              <div className="text-muted-foreground">Current overage</div>
              <div className="font-medium">EUR {state.current_overage_eur}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Forecast</div>
              <div className="font-medium">EUR {state.forecast_total_overage_eur}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Current cap</div>
              <div className="font-medium">{state.max_overage_eur ?? "Unlimited"}</div>
            </div>
          </div>
        ) : null}
        <Form {...form}>
          <form
            className="space-y-4"
            onSubmit={form.handleSubmit((values) =>
              authorize.mutate({
                workspaceId,
                max_overage_eur: values.max_overage_eur || null,
              }),
            )}
          >
            <FormField
              control={form.control}
              name="max_overage_eur"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>EUR cap</FormLabel>
                  <FormControl>
                    <Input inputMode="decimal" placeholder="50.00" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={authorize.isPending}>
                Authorise overage
              </Button>
              {state?.is_authorized ? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={revoke.isPending}
                  onClick={() => revoke.mutate(workspaceId)}
                >
                  Revoke
                </Button>
              ) : null}
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
