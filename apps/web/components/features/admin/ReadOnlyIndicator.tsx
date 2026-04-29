"use client";

import { Eye, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useToggleReadOnlyMode } from "@/lib/hooks/use-admin-mutations";
import { useAdminStore } from "@/lib/stores/admin-store";

export function ReadOnlyIndicator() {
  const readOnlyMode = useAdminStore((state) => state.readOnlyMode);
  const setReadOnlyMode = useAdminStore((state) => state.setReadOnlyMode);
  const toggle = useToggleReadOnlyMode();

  function setMode(enabled: boolean) {
    setReadOnlyMode(enabled);
    toggle.mutate({ enabled });
  }

  return (
    <div className="flex items-center gap-2 rounded-md border px-2 py-1 text-xs">
      {readOnlyMode ? <Eye className="h-3.5 w-3.5" /> : <Pencil className="h-3.5 w-3.5" />}
      <span>{readOnlyMode ? "Read-only" : "Write"}</span>
      <Switch
        checked={readOnlyMode}
        onCheckedChange={setMode}
        aria-label="Toggle read-only mode"
      />
      {readOnlyMode ? (
        <Button variant="ghost" size="sm" className="h-6 px-2" onClick={() => setMode(false)}>
          Off
        </Button>
      ) : null}
    </div>
  );
}
