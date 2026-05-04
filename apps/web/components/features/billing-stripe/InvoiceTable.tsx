"use client";

import { Download } from "lucide-react";
import type { InvoiceSummary } from "@/lib/api/billing-stripe";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function InvoiceTable({ invoices }: { invoices: InvoiceSummary[] }) {
  if (invoices.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No invoices yet.</p>
    );
  }
  return (
    <div className="overflow-hidden rounded-md border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-4 py-3">Invoice</th>
            <th className="px-4 py-3">Period</th>
            <th className="px-4 py-3">Amount</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3 text-right">PDF</th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((inv) => (
            <tr key={inv.id} className="border-t">
              <td className="px-4 py-3 font-medium">
                {inv.invoice_number ?? inv.stripe_invoice_id}
              </td>
              <td className="px-4 py-3 text-xs text-muted-foreground">
                {inv.period_start
                  ? new Date(inv.period_start).toLocaleDateString()
                  : "—"}{" "}
                –{" "}
                {inv.period_end
                  ? new Date(inv.period_end).toLocaleDateString()
                  : "—"}
              </td>
              <td className="px-4 py-3">
                {inv.currency} {inv.amount_total}
                <span className="ml-1 text-xs text-muted-foreground">
                  ({inv.currency} {inv.amount_tax} tax)
                </span>
              </td>
              <td className="px-4 py-3">
                <Badge
                  variant={
                    inv.status === "paid"
                      ? "default"
                      : inv.status === "open"
                        ? "secondary"
                        : "destructive"
                  }
                >
                  {inv.status}
                </Badge>
              </td>
              <td className="px-4 py-3 text-right">
                {inv.pdf_url ? (
                  <Button asChild size="sm" variant="outline">
                    <a href={inv.pdf_url} target="_blank" rel="noreferrer">
                      <Download className="mr-2 h-4 w-4" />
                      Download
                    </a>
                  </Button>
                ) : (
                  <span className="text-xs text-muted-foreground">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
