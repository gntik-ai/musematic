"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/auth-store";

const steps = ["Navigation", "Users", "Workspaces", "Audit", "Help"] as const;

export function AdminTour() {
  const user = useAuthStore((state) => state.user);
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(false);
  const storageKey = useMemo(
    () => `admin-tour-completed:${user?.id ?? user?.email ?? "anonymous"}`,
    [user?.email, user?.id],
  );
  const roles = user?.roles ?? [];
  const isSuperAdmin = roles.includes("superadmin");

  useEffect(() => {
    if (isSuperAdmin) {
      setVisible(false);
      return;
    }
    setVisible(window.localStorage.getItem(storageKey) !== "true");
  }, [isSuperAdmin, storageKey]);

  function completeTour() {
    window.localStorage.setItem(storageKey, "true");
    setVisible(false);
  }

  if (!visible) {
    return null;
  }

  return (
    <div className="rounded-md border bg-card p-4">
      <div className="text-sm font-medium">{steps[index]}</div>
      <div className="mt-3 flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => setIndex((value) => Math.max(0, value - 1))}
          disabled={index === 0}
        >
          Back
        </Button>
        <Button
          size="sm"
          onClick={() => {
            if (index === steps.length - 1) {
              completeTour();
              return;
            }
            setIndex((value) => value + 1);
          }}
        >
          {index === steps.length - 1 ? "Done" : "Next"}
        </Button>
        <Button size="sm" variant="ghost" onClick={completeTour}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}
