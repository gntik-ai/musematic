"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { DataTable } from "@/components/shared/DataTable";
import { useCertificationExpiries, type CertificationExpirySort, type CertificationExpiryRow } from "@/lib/hooks/use-certification-expiries";

const STATUS_META = {
  green: { className: "bg-emerald-500/10 text-emerald-700", label: "Valid" },
  amber: { className: "bg-amber-500/10 text-amber-700", label: "Expiring" },
  red: { className: "bg-red-500/10 text-red-700", label: "Attention" },
} as const;

export interface CertificationExpiryDashboardProps {
  defaultSort?: CertificationExpirySort;
}

export function CertificationExpiryDashboard({
  defaultSort = "expires_at_asc",
}: CertificationExpiryDashboardProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sort = (searchParams.get("sort") as CertificationExpirySort | null) ?? defaultSort;
  const { items, isLoading } = useCertificationExpiries(sort);

  const columns = useMemo<ColumnDef<CertificationExpiryRow>[]>(
    () => [
      { accessorKey: "agentFqn", header: "Agent FQN" },
      { accessorKey: "certifierName", header: "Certifier" },
      {
        accessorKey: "issuedAt",
        header: "Issued",
        cell: ({ row }) => new Date(row.original.issuedAt).toLocaleDateString(),
      },
      {
        accessorKey: "expiresAt",
        header: "Expires",
        cell: ({ row }) => row.original.expiresAt ? new Date(row.original.expiresAt).toLocaleDateString() : "—",
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => {
          const meta = STATUS_META[row.original.status];
          return <Badge className={meta.className} variant="secondary">{meta.label}</Badge>;
        },
      },
    ],
    [],
  );

  return (
    <DataTable
      columns={columns}
      data={items}
      enableFiltering={false}
      isLoading={isLoading}
      totalCount={items.length}
      onSortingChange={(sorting: SortingState) => {
        const first = sorting[0];
        let nextSort: CertificationExpirySort = "expires_at_asc";
        if (first?.id === "agentFqn") {
          nextSort = "agent_fqn";
        } else if (first?.id === "certifierName") {
          nextSort = "certifier_name";
        }
        const nextParams = new URLSearchParams(searchParams.toString());
        nextParams.set("sort", nextSort);
        router.replace(`${pathname}?${nextParams.toString()}`);
      }}
    />
  );
}
