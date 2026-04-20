"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { useAgentContracts } from "@/lib/hooks/use-agent-contracts";

export interface AgentProfileContractsTabProps {
  agentId: string;
}

export function AgentProfileContractsTab({ agentId }: AgentProfileContractsTabProps) {
  const { contracts, isLoading } = useAgentContracts(agentId);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [diffOpen, setDiffOpen] = useState(false);
  const selectedContracts = useMemo(
    () => contracts.filter((contract) => selectedIds.includes(contract.id)).slice(0, 2),
    [contracts, selectedIds],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Contracts</h2>
          <p className="text-sm text-muted-foreground">
            Compare active and superseded contracts before changing agent expectations.
          </p>
        </div>
        <Button disabled={selectedIds.length !== 2} variant="outline" onClick={() => setDiffOpen(true)}>
          Diff
        </Button>
      </div>

      <div className="space-y-3">
        {isLoading ? (
          <div className="h-24 animate-pulse rounded-2xl bg-muted/50" />
        ) : contracts.length === 0 ? (
          <p className="rounded-xl border border-border/70 bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
            No contracts recorded for this agent yet.
          </p>
        ) : (
          contracts.map((contract) => {
            const checked = selectedIds.includes(contract.id);
            return (
              <label
                key={contract.id}
                className="flex cursor-pointer items-start gap-4 rounded-2xl border border-border/70 bg-card/80 p-4"
              >
                <Checkbox
                  checked={checked}
                  onChange={(event) => {
                    const nextChecked = event.currentTarget.checked;
                    setSelectedIds((current) => {
                      if (!nextChecked) {
                        return current.filter((id) => id !== contract.id);
                      }
                      return [...current.filter((id) => id !== contract.id), contract.id].slice(-2);
                    });
                  }}
                />
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium">Version {contract.version}</p>
                    <Badge variant={contract.status === "active" ? "default" : "secondary"}>
                      {contract.status}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">{contract.documentExcerpt}</p>
                  <p className="text-xs text-muted-foreground">
                    Published {new Date(contract.publishedAt).toLocaleString()}
                  </p>
                </div>
              </label>
            );
          })
        )}
      </div>

      <Dialog open={diffOpen} onOpenChange={setDiffOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Contract diff</DialogTitle>
            <DialogDescription>
              Review two contract revisions side by side.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 md:grid-cols-2">
            {selectedContracts.map((contract) => (
              <div key={contract.id} className="rounded-2xl border border-border/70 bg-muted/20 p-4">
                <div className="mb-3 flex items-center gap-2">
                  <Badge variant={contract.status === "active" ? "default" : "secondary"}>
                    {contract.status}
                  </Badge>
                  <span className="text-sm font-medium">Version {contract.version}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                  {contract.documentExcerpt}
                </p>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDiffOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
