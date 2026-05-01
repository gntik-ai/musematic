"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ComponentRow } from "@/components/ComponentRow";
import { IncidentTimeline } from "@/components/IncidentTimeline";
import { StatusBanner } from "@/components/StatusBanner";
import { getDictionary, resolveLocale } from "@/lib/i18n";
import {
  type SnapshotLoadResult,
  embeddedSnapshot,
  loadStatusSnapshot,
} from "@/lib/status-client";

export function StatusPageClient() {
  const [locale, setLocale] = useState(resolveLocale());
  const dictionary = getDictionary(locale);
  const [result, setResult] = useState<SnapshotLoadResult>({
    snapshot: embeddedSnapshot,
    source: "embedded",
    stale: true,
  });

  useEffect(() => {
    let mounted = true;
    setLocale(resolveLocale(navigator.languages?.join(",") ?? navigator.language));
    void loadStatusSnapshot().then((nextResult) => {
      if (mounted) {
        setResult(nextResult);
      }
    });
    return () => {
      mounted = false;
    };
  }, []);

  const snapshot = result.snapshot;
  const stateLabel = dictionary.statusLabels[snapshot.overall_state];
  const incidentCount = snapshot.active_incidents.length;
  const bannerDetail = useMemo(() => {
    if (result.stale) {
      return `${dictionary.lastUpdated}: ${new Date(snapshot.generated_at).toLocaleString()}`;
    }
    if (snapshot.active_maintenance) {
      return `${snapshot.active_maintenance.title} ends ${new Date(
        snapshot.active_maintenance.ends_at,
      ).toLocaleString()}`;
    }
    if (incidentCount > 0) {
      return `${incidentCount} active incident${incidentCount === 1 ? "" : "s"} affecting platform components.`;
    }
    return `${dictionary.lastUpdated}: ${new Date(snapshot.generated_at).toLocaleString()}`;
  }, [dictionary.lastUpdated, incidentCount, result.stale, snapshot]);

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-6 sm:px-6 lg:px-8">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <Link href="/" className="text-lg font-semibold tracking-normal">
            {dictionary.pageTitle}
          </Link>
          <nav aria-label="Status navigation" className="flex flex-wrap gap-2 text-sm">
            <Link className="rounded-md border px-3 py-2 hover:bg-muted" href="/history/">
              {dictionary.recentHistory}
            </Link>
            <Link className="rounded-md border px-3 py-2 hover:bg-muted" href="/subscribe/">
              {dictionary.subscribeToUpdates}
            </Link>
          </nav>
        </header>

        <StatusBanner
          state={snapshot.overall_state}
          label={stateLabel}
          detail={bannerDetail}
          stale={result.stale}
        />

        <section className="grid gap-4 md:grid-cols-3">
          <div className="rounded-md border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">{dictionary.lastUpdated}</p>
            <p className="mt-2 text-lg font-semibold">
              {new Date(snapshot.generated_at).toLocaleString()}
            </p>
          </div>
          <div className="rounded-md border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">{dictionary.thirtyDayUptime}</p>
            <p className="mt-2 text-lg font-semibold">
              {averageUptime(snapshot.components).toFixed(2)}%
            </p>
          </div>
          <div className="rounded-md border border-border bg-card p-4">
            <p className="text-sm text-muted-foreground">Snapshot source</p>
            <p className="mt-2 text-lg font-semibold">{result.source}</p>
          </div>
        </section>

        <section aria-labelledby="components-heading" className="rounded-md border bg-card">
          <div className="border-b border-border px-4 py-3">
            <h2 id="components-heading" className="text-lg font-semibold">
              Components
            </h2>
          </div>
          <div>
            {snapshot.components.map((component) => (
              <ComponentRow
                key={component.id}
                component={component}
                label={dictionary.statusLabels[component.state]}
              />
            ))}
          </div>
        </section>

        <section aria-labelledby="incidents-heading" className="grid gap-4 md:grid-cols-[2fr_1fr]">
          <div>
            <h2 id="incidents-heading" className="mb-3 text-lg font-semibold">
              {dictionary.activeIncidents}
            </h2>
            <IncidentTimeline
              incidents={snapshot.active_incidents}
              emptyLabel={dictionary.noIncidents}
            />
          </div>
          <aside className="rounded-md border border-border bg-card p-4">
            <h2 className="text-lg font-semibold">{dictionary.feedLinks}</h2>
            <div className="mt-4 grid gap-2 text-sm">
              <a className="rounded-md border px-3 py-2 hover:bg-muted" href="/api/v1/public/status/feed.rss">
                RSS
              </a>
              <a className="rounded-md border px-3 py-2 hover:bg-muted" href="/api/v1/public/status/feed.atom">
                Atom
              </a>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}

function averageUptime(components: { uptime_30d_pct?: number | null }[]) {
  if (components.length === 0) {
    return 100;
  }
  const total = components.reduce(
    (sum, component) => sum + (component.uptime_30d_pct ?? 100),
    0,
  );
  return total / components.length;
}
