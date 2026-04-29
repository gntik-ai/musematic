"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

const steps = ["Navigation", "Users", "Workspaces", "Audit", "Help"] as const;

export function AdminTour() {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);

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
              setVisible(false);
              return;
            }
            setIndex((value) => value + 1);
          }}
        >
          {index === steps.length - 1 ? "Done" : "Next"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setVisible(false)}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}
