"use client";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import type { SavedViewResponse, TaggableEntityType } from "@/lib/api/tagging";
import { useSavedViewShare, useSavedViews } from "@/lib/api/tagging";
import { Share2 } from "lucide-react";

interface SavedViewPickerProps {
  entityType: TaggableEntityType;
  workspaceId: string | null;
  onApply: (view: SavedViewResponse) => void;
}

export function SavedViewPicker({ entityType, workspaceId, onApply }: SavedViewPickerProps) {
  const { data } = useSavedViews(entityType, workspaceId);
  const share = useSavedViewShare(entityType, workspaceId);
  const views = data ?? [];

  return (
    <div className="flex items-center gap-2">
      <Select
        aria-label="Saved view"
        className="w-56"
        onChange={(event) => {
          const viewId = event.target.value;
          const view = views.find((item) => item.id === viewId);
          if (view) {
            onApply(view);
          }
        }}
      >
        <option value="">Saved view</option>
        {views.map((view) => (
          <option key={view.id} value={view.id}>
            {view.name}
            {view.is_shared ? " · shared" : ""}
            {view.is_orphan_transferred || view.is_orphan ? " · former member" : ""}
          </option>
        ))}
      </Select>
      {views.find((view) => view.is_owner) ? (
        <Button
          aria-label="Toggle share"
          onClick={() => {
            const view = views.find((item) => item.is_owner);
            if (view) {
              share.mutate({ id: view.id, shared: !view.is_shared });
            }
          }}
          size="icon"
          variant="outline"
        >
          <Share2 className="h-4 w-4" aria-hidden="true" />
        </Button>
      ) : null}
    </div>
  );
}
