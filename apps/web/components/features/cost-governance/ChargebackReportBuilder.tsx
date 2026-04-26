"use client";

import { useMemo, useState } from "react";
import { Download, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ChargebackReportRequest } from "@/lib/api/costs";

interface ChargebackReportBuilderProps {
  isSubmitting?: boolean;
  workspaceId?: string | null;
  onExport: (payload: ChargebackReportRequest, format: "csv" | "ndjson") => void;
  onGenerate: (payload: ChargebackReportRequest) => void;
}

const GROUP_OPTIONS = ["workspace", "agent", "user", "cost_type", "day", "week", "month"];

export function ChargebackReportBuilder({
  isSubmitting = false,
  onExport,
  onGenerate,
  workspaceId,
}: ChargebackReportBuilderProps) {
  const [from, setFrom] = useState(() => new Date(Date.now() - 29 * 86400_000).toISOString().slice(0, 10));
  const [to, setTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [groupBy, setGroupBy] = useState<string[]>(["workspace", "cost_type"]);
  const payload = useMemo<ChargebackReportRequest>(
    () => {
      const basePayload: ChargebackReportRequest = {
        dimensions: groupBy,
        group_by: groupBy,
        since: new Date(`${from}T00:00:00.000Z`).toISOString(),
        until: new Date(`${to}T23:59:59.999Z`).toISOString(),
      };
      return workspaceId ? { ...basePayload, workspace_filter: [workspaceId] } : basePayload;
    },
    [from, groupBy, to, workspaceId],
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="chargeback-from">From</Label>
          <Input id="chargeback-from" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="chargeback-to">To</Label>
          <Input id="chargeback-to" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {GROUP_OPTIONS.map((option) => (
          <label key={option} className="flex items-center gap-2 rounded-lg border p-3 text-sm">
            <Checkbox
              checked={groupBy.includes(option)}
              onChange={(event) => {
                setGroupBy((current) =>
                  event.target.checked
                    ? [...current, option]
                    : current.filter((item) => item !== option),
                );
              }}
            />
            {option}
          </label>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button disabled={isSubmitting || groupBy.length === 0} onClick={() => onGenerate(payload)}>
          <FileText className="mr-2 h-4 w-4" />
          Generate
        </Button>
        <Button disabled={groupBy.length === 0} variant="outline" onClick={() => onExport(payload, "csv")}>
          <Download className="mr-2 h-4 w-4" />
          CSV
        </Button>
        <Button disabled={groupBy.length === 0} variant="outline" onClick={() => onExport(payload, "ndjson")}>
          <Download className="mr-2 h-4 w-4" />
          NDJSON
        </Button>
      </div>
    </div>
  );
}
