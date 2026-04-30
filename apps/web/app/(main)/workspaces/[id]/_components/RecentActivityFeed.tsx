"use client";

import { History } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function labelForActivity(item: Record<string, unknown>): string {
  return String(item.event_type ?? item.action ?? item.type ?? "Workspace event");
}

export function RecentActivityFeed({ items }: { items: Record<string, unknown>[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="h-4 w-4" />
          Recent activity
        </CardTitle>
      </CardHeader>
      <CardContent>
        {items.length ? (
          <ol className="space-y-3">
            {items.slice(0, 10).map((item, index) => (
              <li key={`${labelForActivity(item)}-${index}`} className="rounded-md border p-3">
                <p className="text-sm font-medium">{labelForActivity(item)}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {String(item.created_at ?? item.timestamp ?? "Latest workspace activity")}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">No recent activity recorded.</p>
        )}
      </CardContent>
    </Card>
  );
}
