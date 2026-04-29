"use client";

import { useState } from "react";
import { ChargebackReportBuilder } from "@/components/features/cost-governance/ChargebackReportBuilder";
import { EmptyState } from "@/components/shared/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type ChargebackReportRequest,
  type ChargebackReportResponse,
  exportChargebackReport,
  generateChargebackReport,
} from "@/lib/api/costs";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function CostReportsPage() {
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const [report, setReport] = useState<ChargebackReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const generate = async (payload: ChargebackReportRequest) => {
    setIsLoading(true);
    try {
      setReport(await generateChargebackReport(payload));
    } finally {
      setIsLoading(false);
    }
  };

  const exportReport = async (payload: ChargebackReportRequest, format: "csv" | "ndjson") => {
    const content = await exportChargebackReport(payload, format);
    const blob = new Blob([content], { type: format === "csv" ? "text/csv" : "application/x-ndjson" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `chargeback.${format}`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (!workspaceId) {
    return <EmptyState title="Reports unavailable" description="Select a workspace." />;
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Chargeback Reports</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Builder</CardTitle>
        </CardHeader>
        <CardContent>
          <ChargebackReportBuilder
            isSubmitting={isLoading}
            workspaceId={workspaceId}
            onExport={exportReport}
            onGenerate={generate}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Preview</CardTitle>
        </CardHeader>
        <CardContent>
          {report ? (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Dimensions</TableHead>
                    <TableHead>Total</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Compute</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.rows.map((row, index) => (
                    <TableRow key={`${JSON.stringify(row.dimensions)}-${index}`}>
                      <TableCell className="font-mono text-xs">{JSON.stringify(row.dimensions)}</TableCell>
                      <TableCell>${(Number(row.total_cost_cents) / 100).toFixed(2)}</TableCell>
                      <TableCell>${(Number(row.model_cost_cents) / 100).toFixed(2)}</TableCell>
                      <TableCell>${(Number(row.compute_cost_cents) / 100).toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <EmptyState title="No report" description="Generate a report." />
          )}
        </CardContent>
      </Card>
    </section>
  );
}
