"use client";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { TaggableEntityType } from "@/lib/api/tagging";
import { useSavedViewCreate } from "@/lib/api/tagging";
import { Save } from "lucide-react";
import { useState } from "react";

interface SavedViewSaveDialogProps {
  entityType: TaggableEntityType;
  workspaceId: string | null;
  filters: Record<string, unknown>;
}

export function SavedViewSaveDialog({ entityType, workspaceId, filters }: SavedViewSaveDialogProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [shared, setShared] = useState(false);
  const create = useSavedViewCreate(entityType, workspaceId);

  async function onSave() {
    const normalized = name.trim();
    if (!normalized) {
      return;
    }
    await create.mutateAsync({
      workspace_id: workspaceId,
      name: normalized,
      entity_type: entityType,
      filters,
      shared,
    });
    setName("");
    setShared(false);
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button aria-label="Save view" size="icon" variant="outline">
          <Save className="h-4 w-4" aria-hidden="true" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Save View</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3">
          <Input aria-label="Saved view name" onChange={(event) => setName(event.target.value)} value={name} />
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={shared} onCheckedChange={setShared} />
            Share with workspace
          </label>
        </div>
        <DialogFooter>
          <Button disabled={!name.trim()} onClick={onSave}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
