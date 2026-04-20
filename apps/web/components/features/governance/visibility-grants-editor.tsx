"use client";

import { useEffect, useState } from "react";
import { Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { describeAudience } from "@/lib/validators/fqn-pattern";
import { useVisibilityGrantMutations, useVisibilityGrants } from "@/lib/hooks/use-visibility-grants";

interface VisibilityGrantsEditorProps {
  workspaceId: string;
}

export function VisibilityGrantsEditor({ workspaceId }: VisibilityGrantsEditorProps) {
  const { grants } = useVisibilityGrants(workspaceId);
  const mutation = useVisibilityGrantMutations(workspaceId);
  const [patterns, setPatterns] = useState<string[]>([]);

  useEffect(() => {
    setPatterns(grants.map((grant) => grant.pattern));
  }, [grants]);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2 text-brand-accent">
          <Eye className="h-4 w-4" />
          <span className="text-sm font-semibold uppercase tracking-[0.2em]">Visibility grants</span>
        </div>
        <CardTitle>Workspace visibility rules</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {patterns.map((pattern, index) => (
          <div className="grid gap-2 rounded-xl border border-border/60 p-4 md:grid-cols-[minmax(0,1fr)_220px_auto]" key={`${pattern}-${index}`}>
            <Input
              value={pattern}
              onChange={(event) => {
                const next = [...patterns];
                next[index] = event.target.value;
                setPatterns(next);
              }}
            />
            <div className="text-sm text-muted-foreground">{describeAudience(pattern)}</div>
            <Button
              type="button"
              variant="outline"
              onClick={() => setPatterns((current) => current.filter((_, itemIndex) => itemIndex !== index))}
            >
              Remove
            </Button>
          </div>
        ))}
        <div className="flex flex-wrap justify-between gap-3">
          <Button type="button" variant="outline" onClick={() => setPatterns((current) => [...current, "workspace:*/agent:*"])}>
            Add pattern
          </Button>
          <Button disabled={mutation.isPending} onClick={() => mutation.mutate(patterns.filter(Boolean))}>
            Save visibility grants
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
