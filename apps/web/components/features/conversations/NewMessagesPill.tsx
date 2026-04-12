"use client";

import { Button } from "@/components/ui/button";

interface NewMessagesPillProps {
  count: number;
  onClick: () => void;
}

export function NewMessagesPill({
  count,
  onClick,
}: NewMessagesPillProps) {
  if (count <= 0) {
    return null;
  }

  return (
    <div className="pointer-events-none absolute bottom-6 left-1/2 z-20 -translate-x-1/2">
      <Button
        aria-label={`${count} new messages, scroll to bottom`}
        className="pointer-events-auto rounded-full shadow-lg"
        onClick={onClick}
        role="button"
        size="sm"
      >
        ↓ {count} new message{count === 1 ? "" : "s"}
      </Button>
    </div>
  );
}
