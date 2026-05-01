"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { StatusBanner } from "@/components/StatusBanner";
import { getDictionary, resolveLocale } from "@/lib/i18n";
import {
  type PlatformStatusSnapshot,
  embeddedSnapshot,
  loadStatusSnapshot,
} from "@/lib/status-client";

type ComponentDetailClientProps = {
  componentId: string;
};

export function ComponentDetailClient({ componentId }: ComponentDetailClientProps) {
  const [locale, setLocale] = useState(resolveLocale());
  const dictionary = getDictionary(locale);
  const [snapshot, setSnapshot] = useState<PlatformStatusSnapshot>(embeddedSnapshot);

  useEffect(() => {
    let mounted = true;
    setLocale(resolveLocale(navigator.languages?.join(",") ?? navigator.language));
    void loadStatusSnapshot().then((result) => {
      if (mounted) {
        setSnapshot(result.snapshot);
      }
    });
    return () => {
      mounted = false;
    };
  }, []);

  const component = snapshot.components.find((item) => item.id === componentId);
  const history = useMemo(
    () => buildHistory(snapshot, componentId),
    [componentId, snapshot],
  );

  if (!component) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-6 px-4 py-8">
        <Link href="/" className="text-sm font-medium text-muted-foreground hover:underline">
          Back to status
        </Link>
        <h1 className="text-2xl font-semibold">Component unavailable</h1>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-6 px-4 py-8">
      <Link href="/" className="text-sm font-medium text-muted-foreground hover:underline">
        Back to status
      </Link>
      <StatusBanner
        state={component.state}
        label={dictionary.statusLabels[component.state]}
        detail={`${component.name} checked ${new Date(component.last_check_at).toLocaleString()}`}
      />
      <section className="rounded-md border border-border bg-card p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">{component.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {dictionary.thirtyDayUptime}: {(component.uptime_30d_pct ?? 100).toFixed(2)}%
            </p>
          </div>
          <p className="font-mono text-sm">{component.id}</p>
        </div>
        <HistoryChart points={history} />
      </section>
    </main>
  );
}

function buildHistory(snapshot: PlatformStatusSnapshot, componentId: string) {
  const current = snapshot.components.find((item) => item.id === componentId);
  return Array.from({ length: 30 }, (_, index) => ({
    day: index + 1,
    state: current?.state ?? "operational",
  }));
}

function HistoryChart({ points }: { points: { day: number; state: string }[] }) {
  const colorForState = (state: string) => {
    if (state === "operational") return "#10b981";
    if (state === "degraded") return "#f59e0b";
    if (state === "partial_outage") return "#f97316";
    if (state === "maintenance") return "#0ea5e9";
    return "#ef4444";
  };

  return (
    <svg
      className="mt-6 h-28 w-full"
      role="img"
      aria-label="30-day component status history"
      viewBox="0 0 300 90"
      preserveAspectRatio="none"
    >
      {points.map((point, index) => (
        <rect
          key={point.day}
          x={index * 10}
          y="18"
          width="7"
          height="54"
          rx="2"
          fill={colorForState(point.state)}
        />
      ))}
    </svg>
  );
}
