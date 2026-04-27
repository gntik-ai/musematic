"use client";

import type { VersionDiffResponse } from "@/lib/api/creator-uis";

export function VersionDiffViewer({ diff }: { diff?: VersionDiffResponse }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-lg bg-muted p-4 text-xs">
      {JSON.stringify(diff ?? { added: {}, removed: {}, modified: {} }, null, 2)}
    </pre>
  );
}

