"use client";

/**
 * UPD-050 T029 — Per-knob editor for the abuse-prevention settings.
 *
 * Renders a single setting (label, current value, save action). The
 * value type is inferred from the current value's runtime type
 * (number / boolean / string). Validation errors from the PATCH are
 * surfaced inline.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { useUpdateAbusePreventionSetting } from "@/lib/hooks/use-abuse-prevention-settings";

export interface ThresholdEditorProps {
  settingKey: string;
  currentValue: unknown;
  description?: string | undefined;
}

function isNumber(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

function isBoolean(v: unknown): v is boolean {
  return typeof v === "boolean";
}

export function ThresholdEditor({
  settingKey,
  currentValue,
  description,
}: ThresholdEditorProps) {
  const [draft, setDraft] = useState<unknown>(currentValue);
  const [error, setError] = useState<string | null>(null);
  const updateSetting = useUpdateAbusePreventionSetting();

  const onSave = async () => {
    setError(null);
    try {
      await updateSetting.mutateAsync({ key: settingKey, value: draft });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  };

  return (
    <div
      className="grid gap-2 rounded-md border bg-card p-4"
      data-testid={`threshold-editor-${settingKey}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Label className="font-mono text-sm">{settingKey}</Label>
          {description ? (
            <p className="text-xs text-muted-foreground">{description}</p>
          ) : null}
        </div>
        <Button
          size="sm"
          onClick={onSave}
          disabled={updateSetting.isPending || draft === currentValue}
        >
          Save
        </Button>
      </div>
      {isBoolean(currentValue) ? (
        <Switch
          checked={isBoolean(draft) ? draft : Boolean(draft)}
          onCheckedChange={(checked) => setDraft(checked)}
          data-testid={`threshold-editor-${settingKey}-switch`}
        />
      ) : isNumber(currentValue) ? (
        <Input
          type="number"
          value={isNumber(draft) ? draft : Number(draft)}
          onChange={(e) => setDraft(Number(e.target.value))}
          data-testid={`threshold-editor-${settingKey}-number`}
        />
      ) : (
        <Input
          value={typeof draft === "string" ? draft : JSON.stringify(draft)}
          onChange={(e) => setDraft(e.target.value)}
          data-testid={`threshold-editor-${settingKey}-text`}
        />
      )}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}

export function ThresholdEditorSkeleton() {
  return (
    <div className="grid gap-2 rounded-md border bg-card p-4">
      <Skeleton className="h-6 w-2/3" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}
