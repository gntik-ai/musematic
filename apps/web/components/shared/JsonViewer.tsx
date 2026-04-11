"use client";

import { ChevronRight, Copy } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";

function JsonNode({
  value,
  depth,
  maxDepth,
  label,
}: {
  value: unknown;
  depth: number;
  maxDepth: number;
  label?: string;
}) {
  const isExpandable = typeof value === "object" && value !== null;
  const defaultOpen = depth < maxDepth;
  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item] as const)
    : isExpandable
      ? Object.entries(value as Record<string, unknown>)
      : [];

  const renderScalar = () => {
    if (value === null) {
      return <span className="italic text-muted-foreground">null</span>;
    }
    if (typeof value === "string") {
      return <span className="text-green-600 dark:text-green-400">"{value}"</span>;
    }
    if (typeof value === "number") {
      return <span className="text-amber-600 dark:text-amber-300">{value}</span>;
    }
    if (typeof value === "boolean") {
      return <span className="text-purple-600 dark:text-purple-300">{String(value)}</span>;
    }
    return <span>{String(value)}</span>;
  };

  if (!isExpandable) {
    return (
      <div className="font-mono text-sm">
        {label ? <span className="mr-2 text-blue-500 dark:text-blue-300">{label}:</span> : null}
        {renderScalar()}
      </div>
    );
  }

  const count = entries.length;
  const openLabel = Array.isArray(value) ? `[ ${count} ]` : `{ ${count} }`;

  return (
    <Collapsible defaultOpen={defaultOpen}>
      <CollapsibleTrigger className="flex items-center gap-2 font-mono text-sm">
        <ChevronRight className="h-3.5 w-3.5" />
        {label ? <span className="text-blue-500 dark:text-blue-300">{label}</span> : <span>root</span>}
        <span className="text-muted-foreground">{openLabel}</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 space-y-1 border-l border-border pl-4">
          {entries.map(([key, item]) => (
            <JsonNode key={key} depth={depth + 1} label={key} maxDepth={maxDepth} value={item} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function JsonViewer({
  value,
  maxDepth = 1,
}: {
  value: unknown;
  maxDepth?: number;
}) {
  return (
    <div className="rounded-xl border border-border bg-card/80 p-4">
      <div className="mb-3 flex justify-end">
        <Button size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(JSON.stringify(value, null, 2))}>
          <Copy className="h-4 w-4" />
          Copy
        </Button>
      </div>
      <JsonNode depth={0} maxDepth={maxDepth} value={value} />
    </div>
  );
}
