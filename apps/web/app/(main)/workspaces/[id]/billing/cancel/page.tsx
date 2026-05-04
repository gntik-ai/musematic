"use client";

import { useParams, useRouter } from "next/navigation";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { CancelForm } from "@/components/features/billing-stripe/CancelForm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceBilling } from "@/lib/hooks/use-workspace-billing";

export default function WorkspaceBillingCancelPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const billing = useWorkspaceBilling(params.id);

  return (
    <WorkspaceOwnerLayout
      title="Cancel subscription"
      description="Cancel at the end of the current billing period — Pro features stay available until then."
    >
      <Card>
        <CardHeader>
          <CardTitle>Subscription</CardTitle>
        </CardHeader>
        <CardContent>
          {billing.isLoading ? <Skeleton className="h-32 rounded-md" /> : null}
          {billing.data ? (
            <CancelForm
              workspaceId={params.id}
              status={billing.data.subscription.status}
              onSuccess={() => router.push(`/workspaces/${params.id}/billing`)}
            />
          ) : null}
        </CardContent>
      </Card>
    </WorkspaceOwnerLayout>
  );
}
