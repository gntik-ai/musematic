"use client";

import { type ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/shared/DataTable";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type {
  BenchmarkCaseResponse,
  JudgeVerdictResponse,
} from "@/types/evaluation";

export interface VerdictTableProps {
  verdicts: JudgeVerdictResponse[];
  cases: BenchmarkCaseResponse[];
  total: number;
  page: number;
  onPageChange: (page: number) => void;
}

interface VerdictTableRow {
  id: string;
  caseText: string;
  expectedOutput: string;
  actualOutput: string;
  score: number | null;
  passed: boolean | null;
  status: JudgeVerdictResponse["status"];
  errorDetail: string | null;
}

function truncate(value: string, maxLength: number): string {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value;
}

function resolveCaseText(
  verdict: JudgeVerdictResponse,
  cases: BenchmarkCaseResponse[],
): string {
  const matchingCase = cases.find((entry) => entry.id === verdict.benchmark_case_id);
  const prompt =
    typeof matchingCase?.input_data.prompt === "string"
      ? matchingCase.input_data.prompt
      : typeof matchingCase?.input_data.input_prompt === "string"
        ? matchingCase.input_data.input_prompt
        : matchingCase?.category;

  return prompt ? truncate(prompt, 60) : verdict.benchmark_case_id;
}

function resolveExpectedOutput(
  verdict: JudgeVerdictResponse,
  cases: BenchmarkCaseResponse[],
): string {
  const matchingCase = cases.find((entry) => entry.id === verdict.benchmark_case_id);
  return matchingCase?.expected_output
    ? truncate(matchingCase.expected_output, 80)
    : "—";
}

const columns: ColumnDef<VerdictTableRow>[] = [
  {
    accessorKey: "caseText",
    header: "Case",
  },
  {
    accessorKey: "expectedOutput",
    header: "Expected Output",
  },
  {
    accessorKey: "actualOutput",
    header: "Actual Output",
    cell: ({ row }) => (
      <details className="max-w-xl">
        <summary className="cursor-pointer list-none text-sm text-muted-foreground">
          {truncate(row.original.actualOutput || "—", 80)}
        </summary>
        <div className="mt-2 space-y-2 rounded-lg border border-border/60 bg-muted/20 p-3">
          <p className="whitespace-pre-wrap text-sm">{row.original.actualOutput || "—"}</p>
          {row.original.errorDetail ? (
            <p className="text-sm text-destructive">{row.original.errorDetail}</p>
          ) : null}
        </div>
      </details>
    ),
  },
  {
    id: "score",
    header: "Score",
    cell: ({ row }) =>
      typeof row.original.score === "number"
        ? `${Math.round(row.original.score * 100)}%`
        : "—",
  },
  {
    id: "passFail",
    header: "Pass/Fail",
    cell: ({ row }) => (
      <Badge
        className={
          row.original.passed === true
            ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
            : row.original.passed === false
              ? "bg-destructive/10 text-foreground"
              : "text-muted-foreground"
        }
        variant={row.original.passed === null ? "outline" : "secondary"}
      >
        {row.original.passed === true
          ? "Pass"
          : row.original.passed === false
            ? "Fail"
            : "Unknown"}
      </Badge>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge
        label={row.original.status === "scored" ? "Scored" : "Error"}
        status={row.original.status === "scored" ? "healthy" : "error"}
      />
    ),
  },
];

export function VerdictTable({
  verdicts,
  cases,
  total,
  page,
  onPageChange,
}: VerdictTableProps) {
  const rows: VerdictTableRow[] = verdicts.map((verdict) => ({
    id: verdict.id,
    caseText: resolveCaseText(verdict, cases),
    expectedOutput: resolveExpectedOutput(verdict, cases),
    actualOutput: verdict.actual_output,
    score: verdict.overall_score,
    passed: verdict.passed,
    status: verdict.status,
    errorDetail: verdict.error_detail,
  }));

  const hasPrevious = page > 1;
  const pageSize = verdicts.length || 1;
  const hasNext = page * pageSize < total;

  return (
    <section className="space-y-4">
      <div className="overflow-x-auto">
        <DataTable
          columns={columns}
          data={rows}
          emptyStateMessage="No verdicts available for this run."
          enableFiltering={false}
          hidePagination
          isLoading={false}
        />
      </div>
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Page {page} of {Math.max(1, Math.ceil(total / pageSize))}
        </p>
        <div className="flex gap-2">
          <Button disabled={!hasPrevious} variant="outline" onClick={() => onPageChange(page - 1)}>
            Previous
          </Button>
          <Button disabled={!hasNext} variant="outline" onClick={() => onPageChange(page + 1)}>
            Next
          </Button>
        </div>
      </div>
    </section>
  );
}
