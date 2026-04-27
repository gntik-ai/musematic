"use client";

import { use, useMemo } from "react";

export default function ContractHistoryPage({ params }: { params: Promise<{ fqn: string }> }) {
  const resolvedParams = use(params);
  const fqn = useMemo(() => decodeURIComponent(resolvedParams.fqn), [resolvedParams.fqn]);

  return (
    <section className="space-y-3">
      <p className="text-xs font-semibold uppercase text-brand-accent">{fqn}</p>
      <h1 className="text-3xl font-semibold">Contract History</h1>
      <p className="text-muted-foreground">Contract history will display saved previews and revisions.</p>
    </section>
  );
}

