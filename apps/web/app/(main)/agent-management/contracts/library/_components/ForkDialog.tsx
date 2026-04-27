"use client";

import { useState } from "react";
import { GitFork } from "lucide-react";
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
import { useForkContractTemplate } from "@/lib/hooks/use-contract-templates";

export function ForkDialog({
  templateId,
  templateName,
}: {
  templateId: string;
  templateName: string;
}) {
  const fork = useForkContractTemplate();
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState(`${templateName} copy`);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline">
          <GitFork className="h-4 w-4" />
          Fork
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Fork Template</DialogTitle>
        </DialogHeader>
        <Input value={newName} onChange={(event) => setNewName(event.target.value)} />
        <DialogFooter>
          <Button
            disabled={!newName || fork.isPending}
            type="button"
            onClick={() => {
              fork.mutate({ templateId, newName });
              setOpen(false);
            }}
          >
            Fork
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

