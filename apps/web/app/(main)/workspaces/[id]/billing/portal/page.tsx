"use client";

import { useEffect, useRef } from "react";
import { useParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useStripePortalSession } from "@/lib/hooks/use-billing-stripe";

export default function WorkspaceBillingPortalPage() {
  const params = useParams<{ id: string }>();
  const portal = useStripePortalSession(params.id);
  const triggered = useRef(false);

  useEffect(() => {
    if (triggered.current) return;
    triggered.current = true;
    portal.mutate(undefined, {
      onSuccess: (response) => {
        window.location.assign(response.portal_url);
      },
    });
  }, [portal]);

  return (
    <WorkspaceOwnerLayout
      title="Manage billing"
      description="Open the Stripe Customer Portal to update your card, view invoices, or cancel."
    >
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {portal.isPending ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : null}
            Stripe Customer Portal
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {portal.isPending ? (
            <p className="text-muted-foreground">Opening portal session…</p>
          ) : null}
          {portal.isError ? (
            <Alert variant="destructive">
              <AlertTitle>Portal unavailable</AlertTitle>
              <AlertDescription>
                {portal.error?.message ??
                  "Could not create a portal session. Please try again later."}
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>
    </WorkspaceOwnerLayout>
  );
}
