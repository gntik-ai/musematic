"use client";

import { Archive, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export function PostDowngradeCleanupBanner({
  agents,
  users,
  workspaces,
}: {
  agents: number;
  users: number;
  workspaces: number;
}) {
  const total = agents + users + workspaces;
  if (total <= 0) {
    return null;
  }
  return (
    <div className="flex items-start gap-3 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
      <AlertTriangle className="mt-0.5 h-4 w-4" />
      <div className="min-w-0 flex-1 space-y-3">
        <div className="font-medium">Free limits exceeded</div>
        <div>
          {workspaces} workspaces, {agents} agents, and {users} users are above Free limits.
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={workspaces <= 0}>
            <Archive className="h-4 w-4" />
            Archive workspaces
          </Button>
          <Button size="sm" variant="outline" disabled={agents <= 0}>
            <Archive className="h-4 w-4" />
            Archive agents
          </Button>
          <Button size="sm" variant="outline" disabled={users <= 0}>
            <Archive className="h-4 w-4" />
            Archive users
          </Button>
        </div>
      </div>
    </div>
  );
}
