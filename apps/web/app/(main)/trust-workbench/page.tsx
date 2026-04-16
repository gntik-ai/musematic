"use client";

import { useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Fingerprint, Radar, ShieldCheck } from "lucide-react";
import { CertificationDataTable } from "@/components/features/trust-workbench/CertificationDataTable";
import { Badge } from "@/components/ui/badge";
import { useCertificationQueue } from "@/lib/hooks/use-certifications";
import {
  DEFAULT_CERTIFICATION_QUEUE_FILTERS,
  type CertificationQueueFilters,
} from "@/lib/types/trust-workbench";

function parseFilters(searchParams: URLSearchParams): CertificationQueueFilters {
  const status = searchParams.get("status");
  const sortBy = searchParams.get("sort_by");
  const page = Number(searchParams.get("page") ?? DEFAULT_CERTIFICATION_QUEUE_FILTERS.page);
  const pageSize = Number(
    searchParams.get("page_size") ?? DEFAULT_CERTIFICATION_QUEUE_FILTERS.page_size,
  );

  return {
    status:
      status === "pending" || status === "expiring" || status === "revoked"
        ? status
        : null,
    search: searchParams.get("search") ?? "",
    sort_by:
      sortBy === "urgency" || sortBy === "created" || sortBy === "expiration"
        ? sortBy
        : DEFAULT_CERTIFICATION_QUEUE_FILTERS.sort_by,
    page: Number.isFinite(page) && page > 0 ? page : DEFAULT_CERTIFICATION_QUEUE_FILTERS.page,
    page_size:
      pageSize === 20 || pageSize === 50 || pageSize === 100
        ? pageSize
        : DEFAULT_CERTIFICATION_QUEUE_FILTERS.page_size,
  };
}

function serializeFilters(filters: CertificationQueueFilters): string {
  const params = new URLSearchParams();
  if (filters.status) {
    params.set("status", filters.status);
  }
  if (filters.search) {
    params.set("search", filters.search);
  }
  if (filters.sort_by !== DEFAULT_CERTIFICATION_QUEUE_FILTERS.sort_by) {
    params.set("sort_by", filters.sort_by);
  }
  if (filters.page !== DEFAULT_CERTIFICATION_QUEUE_FILTERS.page) {
    params.set("page", String(filters.page));
  }
  if (filters.page_size !== DEFAULT_CERTIFICATION_QUEUE_FILTERS.page_size) {
    params.set("page_size", String(filters.page_size));
  }

  return params.toString();
}

export default function TrustWorkbenchPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);
  const certificationQueueQuery = useCertificationQueue(filters);

  const updateFilters = (nextValues: Partial<CertificationQueueFilters>) => {
    const nextFilters: CertificationQueueFilters = {
      ...filters,
      ...nextValues,
    };
    const query = serializeFilters(nextFilters);
    router.replace(query ? `${pathname}?${query}` : pathname);
  };

  return (
    <section className="space-y-6">
      <header className="overflow-hidden rounded-[2rem] border bg-[radial-gradient(circle_at_top_left,hsl(var(--brand-accent)/0.18),transparent_26%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--muted)/0.55)_100%)] p-6 shadow-sm">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <Badge className="w-fit bg-background/70 text-foreground" variant="outline">
              Trust governance
            </Badge>
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-border/60 bg-background/75 p-3">
                <ShieldCheck className="h-5 w-5 text-brand-accent" />
              </div>
              <div className="space-y-1">
                <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
                  Trust Workbench
                </h1>
                <p className="text-sm text-muted-foreground md:text-base">
                  Triage certification reviews, trust posture, policy bindings, and privacy impact in one workflow.
                </p>
              </div>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-border/60 bg-background/75 p-4 shadow-sm">
              <ShieldCheck className="h-4 w-4 text-brand-accent" />
              <p className="mt-3 text-sm font-medium">Review queue</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Pending, expiring, and revoked certifications stay in a single triage surface.
              </p>
            </div>
            <div className="rounded-2xl border border-border/60 bg-background/75 p-4 shadow-sm">
              <Radar className="h-4 w-4 text-brand-accent" />
              <p className="mt-3 text-sm font-medium">Trust radar</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Visualize seven trust dimensions before taking a final decision.
              </p>
            </div>
            <div className="rounded-2xl border border-border/60 bg-background/75 p-4 shadow-sm">
              <Fingerprint className="h-4 w-4 text-brand-accent" />
              <p className="mt-3 text-sm font-medium">Governance controls</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Attach effective policies and inspect privacy findings without leaving the record.
              </p>
            </div>
          </div>
        </div>
      </header>
      <CertificationDataTable
        data={certificationQueueQuery.data?.items ?? []}
        filters={filters}
        isLoading={certificationQueueQuery.isLoading}
        onFiltersChange={updateFilters}
        onRowClick={(certificationId) => {
          window.location.assign(
            `/trust-workbench/${encodeURIComponent(certificationId)}`,
          );
        }}
        totalCount={certificationQueueQuery.data?.total ?? 0}
      />
    </section>
  );
}
