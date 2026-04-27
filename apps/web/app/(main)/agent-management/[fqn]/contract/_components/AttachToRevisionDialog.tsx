"use client";

import { useState } from "react";
import { attachContractToRevision } from "@/lib/api/creator-uis";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export function AttachToRevisionDialog({ contractId }: { contractId?: string | null }) {
  const [revisionId, setRevisionId] = useState("");
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button disabled={!contractId} className="w-full" type="button" variant="outline">
          Attach to Revision
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Attach Contract</DialogTitle>
        </DialogHeader>
        <Input
          placeholder="Revision UUID"
          value={revisionId}
          onChange={(event) => setRevisionId(event.target.value)}
        />
        <DialogFooter>
          <Button
            disabled={!contractId || !revisionId}
            type="button"
            onClick={async () => {
              await attachContractToRevision(contractId ?? "", revisionId);
              setOpen(false);
            }}
          >
            Attach
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

