"use client";

import { useEffect } from "react";
import { Check, Loader2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface SettingsFormActionsProps {
  isDirty: boolean;
  isPending: boolean;
  isSaved: boolean;
  onReset: () => void;
  onClearSaved?: () => void;
  disableSave?: boolean;
}

export function SettingsFormActions({
  disableSave = false,
  isDirty,
  isPending,
  isSaved,
  onClearSaved,
  onReset,
}: SettingsFormActionsProps) {
  useEffect(() => {
    if (!isSaved || !onClearSaved) {
      return;
    }

    const timer = window.setTimeout(() => {
      onClearSaved();
    }, 1500);

    return () => window.clearTimeout(timer);
  }, [isSaved, onClearSaved]);

  return (
    <div className="flex flex-wrap items-center justify-end gap-3">
      <Button
        disabled={!isDirty || isPending}
        type="button"
        variant="ghost"
        onClick={onReset}
      >
        <RotateCcw className="h-4 w-4" />
        Reset
      </Button>
      <Button disabled={disableSave || !isDirty || isPending} type="submit">
        {isPending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Saving…
          </>
        ) : isSaved ? (
          <>
            <Check className="h-4 w-4" />
            Saved ✓
          </>
        ) : (
          "Save"
        )}
      </Button>
    </div>
  );
}
