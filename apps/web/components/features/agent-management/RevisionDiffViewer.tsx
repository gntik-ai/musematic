"use client";

import dynamic from "next/dynamic";
import { useTheme } from "next-themes";
import { useMemo } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useRevisionDiff } from "@/lib/hooks/use-agent-revisions";

const MonacoDiffEditor = dynamic(
  async () => {
    const module = await import("@monaco-editor/react");
    return module.DiffEditor;
  },
  {
    ssr: false,
    loading: () => (
      <div className="flex min-h-[480px] flex-col gap-3 rounded-2xl border border-border/60 bg-card/80 p-6">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-full min-h-[380px] rounded-xl" />
      </div>
    ),
  },
);

export interface RevisionDiffViewerProps {
  fqn: string;
  baseRevision: number;
  compareRevision: number;
}

export function RevisionDiffViewer({
  fqn,
  baseRevision,
  compareRevision,
}: RevisionDiffViewerProps) {
  const { resolvedTheme } = useTheme();
  const diffQuery = useRevisionDiff(fqn, baseRevision, compareRevision);
  const editorTheme = useMemo(
    () => (resolvedTheme === "dark" ? "vs-dark" : "light"),
    [resolvedTheme],
  );

  if (diffQuery.isLoading || !diffQuery.data) {
    return (
      <div className="flex min-h-[480px] flex-col gap-3 rounded-2xl border border-border/60 bg-card/80 p-6">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-full min-h-[380px] rounded-xl" />
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-border/60 bg-card/80 shadow-sm">
      <div className="border-b border-border/60 px-4 py-3">
        <p className="text-sm font-medium">
          Revision {baseRevision} vs {compareRevision}
        </p>
      </div>
      <div className="h-[520px]">
        <MonacoDiffEditor
          height="100%"
          language="yaml"
          modified={diffQuery.data.compare_content}
          options={{
            automaticLayout: true,
            fontFamily: "var(--font-mono)",
            fontSize: 13,
            minimap: { enabled: false },
            readOnly: true,
            renderSideBySide: true,
            scrollBeyondLastLine: false,
          }}
          original={diffQuery.data.base_content}
          theme={editorTheme}
        />
      </div>
    </div>
  );
}
