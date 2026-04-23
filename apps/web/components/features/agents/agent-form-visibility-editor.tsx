"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { describeAudience, isValidFqnPattern } from "@/lib/validators/fqn-pattern";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth-store";
import type { FqnPattern } from "@/types/fqn";

export interface AgentFormVisibilityEditorProps {
  value: FqnPattern[];
  onChange: (patterns: FqnPattern[]) => void;
  maxPatterns?: number;
}

const ADMIN_ROLES = new Set(["workspace_admin", "platform_admin", "superadmin"]);

function isWorkspaceWide(pattern: string): boolean {
  return pattern.trim().startsWith("workspace:");
}

export function AgentFormVisibilityEditor({
  value,
  onChange,
  maxPatterns = 20,
}: AgentFormVisibilityEditorProps) {
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const canManageWorkspaceWide = roles.some((role) => ADMIN_ROLES.has(role));

  const updatePattern = (index: number, nextValue: string) => {
    const nextPatterns = [...value];
    nextPatterns[index] = nextValue;
    onChange(nextPatterns);
  };

  const removePattern = (index: number) => {
    onChange(value.filter((_, patternIndex) => patternIndex !== index));
  };

  return (
    <div className="space-y-4 rounded-3xl border border-border/60 bg-card/70 p-5">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">Visibility Patterns</h2>
        <p className="text-sm text-muted-foreground">
          Control which workspaces and agent audiences can discover this agent by FQN pattern.
        </p>
      </div>

      <div className="space-y-3">
        {value.map((pattern, index) => {
          const trimmed = pattern.trim();
          const valid = trimmed.length === 0 || isValidFqnPattern(trimmed);
          const workspaceWideBlocked = isWorkspaceWide(trimmed) && !canManageWorkspaceWide;

          return (
            <div key={`${index}-${pattern}`} className="rounded-2xl border border-border/60 p-3">
              <div className="flex flex-col gap-3 md:flex-row md:items-start">
                <div className="min-w-0 flex-1 space-y-2">
                  <Input
                    aria-label={`Visibility Pattern ${index + 1}`}
                    className={cn(
                      !valid && "border-destructive focus-visible:ring-destructive",
                      workspaceWideBlocked && "border-amber-500 focus-visible:ring-amber-500",
                    )}
                    placeholder="workspace:*/agent:compliance-*"
                    value={pattern}
                    onChange={(event) => updatePattern(index, event.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    {trimmed ? describeAudience(trimmed) : "Enter a pattern to preview the audience."}
                  </p>
                  {!valid ? (
                    <p className="text-xs text-destructive">
                      Pattern must follow namespace or wildcard FQN syntax.
                    </p>
                  ) : null}
                  {workspaceWideBlocked ? (
                    <p className="text-xs text-amber-600">
                      Workspace-wide patterns require the workspace_admin role.
                    </p>
                  ) : null}
                </div>
                <Button
                  aria-label={`Remove pattern ${index + 1}`}
                  size="icon"
                  type="button"
                  variant="ghost"
                  onClick={() => removePattern(index)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          {value.length} / {maxPatterns} patterns configured
        </p>
        <Button
          className="gap-2"
          disabled={value.length >= maxPatterns}
          type="button"
          variant="outline"
          onClick={() => onChange([...value, ""])}
        >
          <Plus className="h-4 w-4" />
          Add Pattern
        </Button>
      </div>
    </div>
  );
}
