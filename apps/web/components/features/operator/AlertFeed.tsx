"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { BellRing } from "lucide-react";
import { AlertFeedItem } from "@/components/features/operator/AlertFeedItem";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAlertFeed } from "@/lib/hooks/use-alert-feed";
import { useAlertFeedStore } from "@/lib/stores/use-alert-feed-store";

export interface AlertFeedProps {
  maxHeight?: string;
}

export function AlertFeed({ maxHeight = "400px" }: AlertFeedProps) {
  useAlertFeed();

  const alerts = useAlertFeedStore((state) => state.alerts);
  const severityFilter = useAlertFeedStore((state) => state.severityFilter);
  const setSeverityFilter = useAlertFeedStore((state) => state.setSeverityFilter);
  const anchorRef = useRef<HTMLDivElement | null>(null);
  const [isPinnedToBottom, setIsPinnedToBottom] = useState(true);

  const filteredAlerts = useMemo(() => {
    const visible =
      severityFilter === "all"
        ? alerts
        : alerts.filter((alert) => alert.severity === severityFilter);

    return [...visible].reverse();
  }, [alerts, severityFilter]);

  useEffect(() => {
    if (isPinnedToBottom) {
      anchorRef.current?.scrollIntoView({ block: "end" });
    }
  }, [filteredAlerts.length, isPinnedToBottom]);

  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader className="space-y-4">
        <div>
          <CardTitle>Alert feed</CardTitle>
          <p className="text-sm text-muted-foreground">
            Live operational alerts flowing from the platform monitoring channel.
          </p>
        </div>
        <Tabs>
          <TabsList className="flex w-full flex-wrap gap-2 rounded-[1.5rem] bg-muted/60 p-2">
            {(["all", "info", "warning", "error", "critical"] as const).map(
              (severity) => (
                <TabsTrigger
                  key={severity}
                  aria-pressed={severityFilter === severity}
                  className={
                    severityFilter === severity ? "bg-background shadow-sm" : undefined
                  }
                  onClick={() => setSeverityFilter(severity)}
                >
                  {severity === "all"
                    ? "All"
                    : severity.charAt(0).toUpperCase() + severity.slice(1)}
                </TabsTrigger>
              ),
            )}
          </TabsList>
        </Tabs>
      </CardHeader>
      <CardContent className="space-y-4">
        <div
          className="space-y-3 overflow-y-auto pr-1"
          style={{ maxHeight }}
          onScroll={(event) => {
            const target = event.currentTarget;
            const nearBottom =
              target.scrollHeight - target.scrollTop - target.clientHeight < 24;
            setIsPinnedToBottom(nearBottom);
          }}
        >
          {filteredAlerts.length === 0 ? (
            <EmptyState
              description="No alerts received yet"
              icon={BellRing}
              title="Alert stream idle"
            />
          ) : (
            filteredAlerts.map((alert) => (
              <AlertFeedItem key={alert.id} alert={alert} />
            ))
          )}
          <div ref={anchorRef} />
        </div>

        {!isPinnedToBottom && filteredAlerts.length > 0 ? (
          <div className="sticky bottom-0 flex justify-end">
            <Button
              onClick={() => {
                anchorRef.current?.scrollIntoView({ block: "end" });
                setIsPinnedToBottom(true);
              }}
              size="sm"
              variant="outline"
            >
              New alerts ↓
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
