"use client";

import { LabelFilterPopover } from "@/components/features/tagging/LabelFilterPopover";
import { SavedViewPicker } from "@/components/features/tagging/SavedViewPicker";
import { SavedViewSaveDialog } from "@/components/features/tagging/SavedViewSaveDialog";
import { TagFilterBar } from "@/components/features/tagging/TagFilterBar";
import type { TaggableEntityType } from "@/lib/api/tagging";
import type { TagLabelFilters } from "@/lib/tagging/filter-query";
import { cn } from "@/lib/utils";

interface TagLabelFilterToolbarProps {
  entityType: TaggableEntityType;
  workspaceId: string | null;
  value: TagLabelFilters;
  savedViewFilters: Record<string, unknown>;
  className?: string | undefined;
  onChange: (nextFilters: TagLabelFilters) => void;
  onApplySavedView: (filters: Record<string, unknown>) => void;
}

export function TagLabelFilterToolbar({
  className,
  entityType,
  workspaceId,
  value,
  savedViewFilters,
  onApplySavedView,
  onChange,
}: TagLabelFilterToolbarProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <SavedViewPicker
        entityType={entityType}
        workspaceId={workspaceId}
        onApply={(view) => onApplySavedView(view.filters)}
      />
      <SavedViewSaveDialog
        entityType={entityType}
        filters={savedViewFilters}
        workspaceId={workspaceId}
      />
      <TagFilterBar
        value={value.tags}
        onChange={(tags) => onChange({ ...value, tags })}
      />
      <LabelFilterPopover
        value={value.labels}
        onChange={(labels) => onChange({ ...value, labels })}
      />
    </div>
  );
}
