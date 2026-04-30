"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface GrantDetail {
  direction: "given" | "received";
  label: string;
  pattern: string;
}

export function GrantDetailPanel({ grant }: { grant: GrantDetail | null }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Grant detail</CardTitle></CardHeader>
      <CardContent>
        {grant ? (
          <dl className="space-y-3 text-sm">
            <div><dt className="text-muted-foreground">Direction</dt><dd>{grant.direction}</dd></div>
            <div><dt className="text-muted-foreground">Label</dt><dd>{grant.label}</dd></div>
            <div><dt className="text-muted-foreground">Pattern</dt><dd className="font-mono text-xs">{grant.pattern}</dd></div>
          </dl>
        ) : (
          <p className="text-sm text-muted-foreground">Select a graph edge to inspect a visibility grant.</p>
        )}
      </CardContent>
    </Card>
  );
}
