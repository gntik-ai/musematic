"use client";

import { Button } from "@/components/ui/button";

export function SampleInputManager({ onLoad }: { onLoad: (value: string) => void }) {
  return (
    <div className="flex gap-2">
      <Button
        size="sm"
        type="button"
        variant="outline"
        onClick={() => onLoad('{"output":{"answer":"ok"},"tokens":120}')}
      >
        Load Passing Sample
      </Button>
      <Button
        size="sm"
        type="button"
        variant="outline"
        onClick={() => onLoad('{"force_violation":true,"tokens":999999}')}
      >
        Load Violation Sample
      </Button>
    </div>
  );
}

