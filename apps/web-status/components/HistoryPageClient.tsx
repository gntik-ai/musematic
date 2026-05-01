"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { IncidentTimeline } from "@/components/IncidentTimeline";
import { getDictionary, resolveLocale } from "@/lib/i18n";
import {
  type PlatformStatusSnapshot,
  embeddedSnapshot,
  loadStatusSnapshot,
} from "@/lib/status-client";

export function HistoryPageClient() {
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

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-6 px-4 py-8">
      <Link href="/" className="text-sm font-medium text-muted-foreground hover:underline">
        Back to status
      </Link>
      <header>
        <h1 className="text-2xl font-semibold">{dictionary.recentHistory}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Resolved incidents and updates from the latest available snapshot.
        </p>
      </header>
      <IncidentTimeline
        incidents={snapshot.recently_resolved_incidents}
        emptyLabel={dictionary.noIncidents}
      />
    </main>
  );
}
