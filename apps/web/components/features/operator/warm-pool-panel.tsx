"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { useWarmPoolStatus } from "@/lib/hooks/use-warm-pool-status";
import { cn } from "@/lib/utils";
import { wsClient } from "@/lib/ws";
import type { WarmPoolProfile } from "@/types/operator";

const DELTA_BADGE = {
  on_target: { className: "bg-emerald-500/10 text-emerald-700", label: "On target" },
  within_20_percent: { className: "bg-amber-500/10 text-amber-700", label: "Within 20%" },
  below_target: { className: "bg-red-500/10 text-red-700", label: "Below target" },
} as const;

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asString(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() !== "" ? value : fallback;
}

export function WarmPoolPanel() {
  const { profiles } = useWarmPoolStatus();
  const [liveProfiles, setLiveProfiles] = useState<WarmPoolProfile[]>(profiles);
  const [selectedProfile, setSelectedProfile] = useState<WarmPoolProfile | null>(null);
  const [flashingProfile, setFlashingProfile] = useState<string | null>(null);

  useEffect(() => {
    setLiveProfiles(profiles);
  }, [profiles]);

  useEffect(() => {
    wsClient.connect();
    const unsubscribe = wsClient.subscribe<Record<string, unknown>>("warm-pool", (event) => {
      if (event.type !== "warm-pool.updated") {
        return;
      }

      const payload = asRecord(event.payload);
      const payloadProfile = asRecord(payload.profile);
      const profileName = asString(payloadProfile.name ?? payload.name, "");
      if (!profileName) {
        return;
      }

      setLiveProfiles((current) =>
        current.map((profile) =>
          profile.name === profileName
            ? {
                ...profile,
                targetReplicas: asNumber(
                  payloadProfile.targetReplicas ?? payload.targetReplicas,
                  profile.targetReplicas,
                ),
                actualReplicas: asNumber(
                  payloadProfile.actualReplicas ?? payload.actualReplicas,
                  profile.actualReplicas,
                ),
                deltaStatus: asString(
                  payloadProfile.deltaStatus ?? payload.deltaStatus,
                  profile.deltaStatus,
                ) as WarmPoolProfile["deltaStatus"],
              }
            : profile,
        ),
      );

      if (asString(payloadProfile.deltaStatus ?? payload.deltaStatus, "") === "below_target") {
        setFlashingProfile(profileName);
        window.setTimeout(
          () => setFlashingProfile((current) => (current === profileName ? null : current)),
          500,
        );
      }
    });

    return () => {
      unsubscribe();
    };
  }, []);

  return (
    <>
      <div className="grid gap-4 md:grid-cols-3">
        {liveProfiles.map((profile) => {
          const meta = DELTA_BADGE[profile.deltaStatus];
          return (
            <Card
              key={profile.name}
              className={cn(flashingProfile === profile.name && "animate-pulse")}
              role="button"
              tabIndex={0}
              onClick={() => setSelectedProfile(profile)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setSelectedProfile(profile);
                }
              }}
            >
              <CardHeader>
                <CardTitle>{profile.name}</CardTitle>
                <CardDescription>
                  {profile.actualReplicas} actual / {profile.targetReplicas} target
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Badge className={meta.className} variant="secondary">
                  {meta.label}
                </Badge>
              </CardContent>
            </Card>
          );
        })}
      </div>
      <Sheet open={Boolean(selectedProfile)} onOpenChange={(open) => !open && setSelectedProfile(null)}>
        <SheetContent>
          <SheetTitle>{selectedProfile?.name ?? "Warm pool profile"}</SheetTitle>
          <SheetDescription>Recent scaling activity</SheetDescription>
          <div className="mt-4 space-y-3">
            {(selectedProfile?.lastScalingEvents ?? []).slice(0, 5).map((event, index) => (
              <div key={`${event.at}-${index}`} className="rounded-2xl border border-border/70 bg-card/80 p-4">
                <p className="font-medium">
                  {event.from} → {event.to}
                </p>
                <p className="text-sm text-muted-foreground">{event.reason}</p>
                <p className="text-xs text-muted-foreground">{new Date(event.at).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
