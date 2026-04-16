"use client";

import { useState } from "react";
import { Info, Plus, Trash2 } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { VisibilityPattern } from "@/lib/types/agent-management";

export interface VisibilityPatternPanelProps {
  patterns: VisibilityPattern[];
  onChange: (patterns: VisibilityPattern[]) => void;
  disabled?: boolean;
}

export function VisibilityPatternPanel({
  patterns,
  onChange,
  disabled = false,
}: VisibilityPatternPanelProps) {
  const [nextPattern, setNextPattern] = useState("");

  return (
    <div className="space-y-4 rounded-2xl border border-border/60 bg-background/70 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="font-medium">Visibility patterns</h3>
          <p className="text-sm text-muted-foreground">
            Control where the agent is visible using FQN-style patterns.
          </p>
        </div>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger>
              <button
                aria-label="Explain visibility patterns"
                className="rounded-md p-1 text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                type="button"
              >
                <Info className="h-4 w-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>
              Patterns can target exact FQNs or wildcard namespaces such as finance-ops:*.
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          disabled={disabled}
          placeholder="finance-ops:*"
          value={nextPattern}
          onChange={(event) => setNextPattern(event.target.value)}
        />
        <Button
          className="gap-2"
          disabled={disabled || nextPattern.trim().length === 0}
          type="button"
          onClick={() => {
            onChange([
              ...patterns,
              {
                pattern: nextPattern.trim(),
                description: null,
              },
            ]);
            setNextPattern("");
          }}
        >
          <Plus className="h-4 w-4" />
          Add pattern
        </Button>
      </div>

      <div className="space-y-2">
        {patterns.map((pattern) => (
          <div
            key={pattern.pattern}
            className="flex items-center justify-between gap-3 rounded-xl border border-border/60 px-3 py-2"
          >
            <div>
              <p className="font-medium">{pattern.pattern}</p>
              <p className="text-xs text-muted-foreground">
                Matches resources routed through this namespace pattern.
              </p>
            </div>
            <Button
              aria-label={`Remove visibility pattern ${pattern.pattern}`}
              disabled={disabled}
              size="icon"
              type="button"
              variant="ghost"
              onClick={() =>
                onChange(
                  patterns.filter((entry) => entry.pattern !== pattern.pattern),
                )
              }
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
