"use client";

import { CheckCircle2, Clock, AlertTriangle, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export interface CascadeStoreProgress {
  store: string;
  status: "pending" | "in_progress" | "completed" | "failed";
  rows_purged?: number | null;
  bytes_freed?: number | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

function statusIcon(status: CascadeStoreProgress["status"]) {
  switch (status) {
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
    case "in_progress":
      return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
    case "failed":
      return <AlertTriangle className="h-4 w-4 text-destructive" />;
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
}

function formatBytes(bytes?: number | null): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let value = bytes;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(1)} ${units[i]}`;
}

export function TenantCascadeProgressTable({
  rows,
}: {
  rows: CascadeStoreProgress[];
}) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Cascade progress will appear once phase 2 begins.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2">Store</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Rows purged</th>
            <th className="px-3 py-2">Bytes freed</th>
            <th className="px-3 py-2">Started</th>
            <th className="px-3 py-2">Completed</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.store} className="border-t">
              <td className="px-3 py-2 font-medium">{row.store}</td>
              <td className="px-3 py-2">
                <span className="inline-flex items-center gap-2">
                  {statusIcon(row.status)}
                  <Badge variant={row.status === "failed" ? "destructive" : "secondary"}>
                    {row.status}
                  </Badge>
                </span>
                {row.error_message ? (
                  <p className="mt-1 max-w-xs text-xs text-destructive">
                    {row.error_message}
                  </p>
                ) : null}
              </td>
              <td className="px-3 py-2 text-muted-foreground">
                {row.rows_purged?.toLocaleString() ?? "—"}
              </td>
              <td className="px-3 py-2 text-muted-foreground">
                {formatBytes(row.bytes_freed)}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {row.started_at ? new Date(row.started_at).toLocaleString() : "—"}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {row.completed_at
                  ? new Date(row.completed_at).toLocaleString()
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
