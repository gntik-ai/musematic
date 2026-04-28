"use client";

import { useState } from "react";
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

export function RealLLMOptInDialog({
  disabled,
  onConfirm,
}: {
  disabled?: boolean;
  onConfirm: () => void;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button disabled={disabled} type="button" variant="outline">
          Real LLM Preview
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm Real LLM Preview</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          This preview can consume model budget and may call external model providers.
        </p>
        <Input
          placeholder="USE_REAL_LLM"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
        />
        <DialogFooter>
          <Button
            disabled={confirmation !== "USE_REAL_LLM"}
            type="button"
            onClick={() => {
              onConfirm();
              setOpen(false);
              setConfirmation("");
            }}
          >
            Confirm
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
