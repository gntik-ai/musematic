"use client";

import { useParams } from "next/navigation";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { InvoiceTable } from "@/components/features/billing-stripe/InvoiceTable";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useStripeInvoices } from "@/lib/hooks/use-billing-stripe";

export default function WorkspaceBillingInvoicesPage() {
  const params = useParams<{ id: string }>();
  const { data, isLoading } = useStripeInvoices(params.id);

  return (
    <WorkspaceOwnerLayout
      title="Invoices"
      description="Stripe-issued invoices for this workspace."
    >
      <Card>
        <CardHeader>
          <CardTitle>Recent invoices</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? <Skeleton className="h-32 rounded-md" /> : null}
          {data ? <InvoiceTable invoices={data.items} /> : null}
        </CardContent>
      </Card>
    </WorkspaceOwnerLayout>
  );
}
