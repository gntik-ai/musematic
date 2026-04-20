"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { useDecommissionWizard } from "@/lib/hooks/use-decommission-wizard";
import { useAuthStore } from "@/store/auth-store";

const ADMIN_ROLES = new Set(["platform_admin", "superadmin"]);

export interface DecommissionWizardProps {
  agentFqn: string;
  isOpen: boolean;
  onClose: () => void;
}

export function DecommissionWizard({ agentFqn, isOpen, onClose }: DecommissionWizardProps) {
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const canDecommission = roles.some((role) => ADMIN_ROLES.has(role));
  const { advance, cancel, confirm, isLoading, plan, stage } = useDecommissionWizard(agentFqn);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if (isOpen && stage === "idle") {
      advance();
    }
    if (!isOpen) {
      cancel();
      setConfirmOpen(false);
    }
  }, [advance, cancel, isOpen, stage]);

  return (
    <>
      <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Decommission agent</DialogTitle>
            <DialogDescription>
              Review downstream impact before moving {agentFqn} out of service.
            </DialogDescription>
          </DialogHeader>
          {stage === "warning" ? (
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>This operation retires the agent from active use and affects downstream dependencies.</p>
              <ul className="list-disc space-y-1 pl-5">
                {(plan?.dependencies ?? []).map((dependency) => (
                  <li key={dependency}>{dependency}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {stage === "dry_run" || stage === "submitting" || stage === "done" ? (
            <div className="space-y-3 text-sm text-muted-foreground">
              {(plan?.dryRunSummary ?? []).map((line) => (
                <p key={line}>{line}</p>
              ))}
              {stage === "done" ? <p className="font-medium text-foreground">Agent marked for decommission.</p> : null}
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => { cancel(); onClose(); }}>
              Cancel
            </Button>
            {stage === "warning" ? (
              <Button disabled={!canDecommission} onClick={advance}>Next</Button>
            ) : null}
            {stage === "dry_run" ? (
              <Button disabled={!canDecommission} onClick={() => setConfirmOpen(true)}>Next</Button>
            ) : null}
            {stage === "done" ? <Button onClick={onClose}>Close</Button> : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        confirmLabel="Decommission"
        description={`Type ${agentFqn} to confirm decommission.`}
        isLoading={isLoading}
        open={confirmOpen}
        requireTypedConfirmation={agentFqn}
        title="Final confirmation"
        variant="destructive"
        onConfirm={() => {
          void confirm().then(() => {
            setConfirmOpen(false);
          });
        }}
        onOpenChange={setConfirmOpen}
      />
    </>
  );
}
