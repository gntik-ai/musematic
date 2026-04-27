"use client";

import { use, useMemo, useState } from "react";
import { VersionHistory } from "@/components/features/agents/VersionHistory";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function ContextProfileHistoryPage({
  params,
}: {
  params: Promise<{ fqn: string }>;
}) {
  const resolvedParams = use(params);
  const fqn = useMemo(() => decodeURIComponent(resolvedParams.fqn), [resolvedParams.fqn]);
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const [profileId, setProfileId] = useState("");

  return (
    <section className="space-y-6">
      <div className="border-b pb-5">
        <p className="text-xs font-semibold uppercase text-brand-accent">{fqn}</p>
        <h1 className="mt-2 text-3xl font-semibold">Context Profile History</h1>
      </div>
      <div className="max-w-xl space-y-2">
        <Label htmlFor="history-profile-id">Profile ID</Label>
        <Input
          id="history-profile-id"
          placeholder="Paste profile UUID"
          value={profileId}
          onChange={(event) => setProfileId(event.target.value)}
        />
      </div>
      <VersionHistory profileId={profileId} workspaceId={workspaceId} />
    </section>
  );
}

