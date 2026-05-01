"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { StatusIndicator } from "@/components/features/platform-status/StatusIndicator";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  usePlatformStatus,
  type IncidentSeverity,
  type MyPlatformIncident,
} from "@/lib/hooks/use-platform-status";
import { cn } from "@/lib/utils";

type BannerKind =
  | "maintenance-scheduled"
  | "maintenance-in-progress"
  | "incident-active"
  | "degraded-performance";

type BannerSeverity = "info" | "warning" | "critical";

interface BannerState {
  kind: BannerKind;
  severity: BannerSeverity;
  fingerprint: string;
  title: string;
  description: string;
  href: string;
  indicatorLabel: string;
}

const publicStatusHost =
  process.env.NEXT_PUBLIC_WEB_STATUS_URL ?? "https://status.musematic.ai";

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function incidentSeverity(severity: IncidentSeverity): BannerSeverity {
  if (severity === "critical") {
    return "critical";
  }
  if (severity === "high" || severity === "warning") {
    return "warning";
  }
  return "info";
}

function pickIncident(incidents: MyPlatformIncident[]): MyPlatformIncident | null {
  const rank: Record<IncidentSeverity, number> = {
    critical: 4,
    high: 3,
    warning: 2,
    info: 1,
  };
  return [...incidents].sort((left, right) => rank[right.severity] - rank[left.severity])[0] ?? null;
}

const bannerClasses: Record<BannerSeverity, string> = {
  info: "border-sky-200 bg-sky-50 text-sky-950",
  warning: "border-amber-200 bg-amber-50 text-amber-950",
  critical: "border-red-200 bg-red-50 text-red-950",
};

export function PlatformStatusBanner() {
  const t = useTranslations("platformStatus");
  const pathname = usePathname();
  const { data } = usePlatformStatus();
  const [dismissedKey, setDismissedKey] = useState<string | null>(null);

  const banner = useMemo<BannerState | null>(() => {
    if (!data) {
      return null;
    }

    if (data.active_maintenance) {
      const now = Date.now();
      const startsAt = new Date(data.active_maintenance.starts_at).getTime();
      const inProgress = startsAt <= now;
      const kind: BannerKind = inProgress
        ? "maintenance-in-progress"
        : "maintenance-scheduled";
      return {
        kind,
        severity: inProgress ? "warning" : "info",
        fingerprint: `${kind}:${data.active_maintenance.window_id}:${data.active_maintenance.ends_at}`,
        title: inProgress
          ? t("maintenanceInProgress")
          : t("maintenanceScheduled"),
        description: t("endsAt", {
          date: formatDateTime(data.active_maintenance.ends_at),
        }),
        href: publicStatusHost,
        indicatorLabel: t(
          inProgress ? "statusLabels.maintenance" : "maintenanceScheduled",
        ),
      };
    }

    const incident = pickIncident(data.active_incidents);
    if (incident) {
      return {
        kind: "incident-active",
        severity: incidentSeverity(incident.severity),
        fingerprint: `incident:${incident.id}:${incident.severity}`,
        title: t("incidentActive"),
        description: incident.title,
        href: `${publicStatusHost}/incidents/${encodeURIComponent(incident.id)}`,
        indicatorLabel: t(`incidentSeverity.${incident.severity}`),
      };
    }

    if (data.overall_state !== "operational") {
      return {
        kind: "degraded-performance",
        severity: data.overall_state === "full_outage" ? "critical" : "info",
        fingerprint: `state:${data.overall_state}`,
        title: t("statusLabels.degraded"),
        description: t(`statusLabels.${data.overall_state}`),
        href: publicStatusHost,
        indicatorLabel: t(`statusLabels.${data.overall_state}`),
      };
    }

    return null;
  }, [data, t]);

  const storageKey = banner ? `platform-status-dismiss:${pathname}:${banner.fingerprint}` : null;

  useEffect(() => {
    if (!storageKey || typeof window === "undefined") {
      setDismissedKey(null);
      return;
    }
    setDismissedKey(sessionStorage.getItem(storageKey) === "1" ? storageKey : null);
  }, [storageKey]);

  if (!banner || dismissedKey === storageKey) {
    return null;
  }

  return (
    <Alert
      aria-live="polite"
      className={cn(
        "rounded-none border-x-0 border-t-0 px-4 py-3",
        bannerClasses[banner.severity],
      )}
      data-testid="platform-status-banner"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <AlertTitle className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <StatusIndicator
              label={banner.indicatorLabel}
              severity={banner.severity}
              state={banner.kind.startsWith("maintenance") ? "maintenance" : undefined}
            />
            <span>{banner.title}</span>
          </AlertTitle>
          <AlertDescription className="text-current/80">
            {banner.description}
          </AlertDescription>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button asChild size="sm" variant="outline">
            <Link href={banner.href}>{banner.kind === "incident-active" ? t("viewIncident") : t("viewStatusPage")}</Link>
          </Button>
          <Button
            aria-label={t("dismiss")}
            size="icon"
            variant="ghost"
            onClick={() => {
              if (storageKey) {
                sessionStorage.setItem(storageKey, "1");
                setDismissedKey(storageKey);
              }
            }}
          >
            <X aria-hidden className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </Alert>
  );
}
