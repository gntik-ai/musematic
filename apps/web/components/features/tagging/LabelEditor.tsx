"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ReservedLabelBadge } from "@/components/features/tagging/ReservedLabelBadge";
import type { TaggableEntityType } from "@/lib/api/tagging";
import { useEntityLabels, useLabelDetach, useLabelUpsert } from "@/lib/api/tagging";
import { Plus, X } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";

const LABEL_KEY_PATTERN = /^[a-zA-Z][a-zA-Z0-9._-]*$/;
const RESERVED_PREFIXES = ["system.", "platform."] as const;

interface LabelEditorProps {
  entityType: TaggableEntityType;
  entityId: string;
  canEditReserved?: boolean;
  readOnly?: boolean;
}

export function LabelEditor({
  entityType,
  entityId,
  canEditReserved = false,
  readOnly = false,
}: LabelEditorProps) {
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const { data } = useEntityLabels(entityType, entityId);
  const upsert = useLabelUpsert(entityType, entityId);
  const detach = useLabelDetach(entityType, entityId);
  const labels = data?.labels ?? [];
  const normalizedKey = key.trim();
  const hasInvalidKey = normalizedKey.length > 0 && !LABEL_KEY_PATTERN.test(normalizedKey);
  const isReservedDraft = RESERVED_PREFIXES.some((prefix) => normalizedKey.startsWith(prefix));
  const reservedDraftBlocked = isReservedDraft && !canEditReserved;
  const canSubmit =
    !readOnly &&
    normalizedKey.length > 0 &&
    LABEL_KEY_PATTERN.test(normalizedKey) &&
    !reservedDraftBlocked;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    await upsert.mutateAsync({ key: normalizedKey, value: value.trim() });
    setKey("");
    setValue("");
  }

  return (
    <div className="space-y-2">
      <div className="grid gap-2">
        {labels.map((item) => {
          const locked = item.is_reserved && !canEditReserved;
          return (
            <div
              className="grid min-h-9 grid-cols-[minmax(8rem,1fr)_minmax(8rem,1fr)_auto] items-center gap-2 rounded-md border border-border px-2 py-1 text-sm"
              key={item.key}
            >
              <span className="font-medium">{item.key}</span>
              <span className="text-muted-foreground">{item.value}</span>
              <div className="flex items-center gap-1">
                {item.is_reserved ? <ReservedLabelBadge /> : null}
                {!readOnly && !locked ? (
                  <Button
                    aria-label={`Remove ${item.key}`}
                    className="h-7 w-7"
                    onClick={() => detach.mutate(item.key)}
                    size="icon"
                    variant="ghost"
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                  </Button>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
      {!readOnly ? (
        <>
          <form
            className="grid grid-cols-[minmax(8rem,1fr)_minmax(8rem,1fr)_auto] gap-2"
            onSubmit={onSubmit}
          >
            <Input
              aria-label="Label key"
              maxLength={128}
              onChange={(event) => setKey(event.target.value)}
              value={key}
            />
            <Input
              aria-label="Label value"
              maxLength={512}
              onChange={(event) => setValue(event.target.value)}
              value={value}
            />
            <Button aria-label="Add label" disabled={!canSubmit} size="icon" type="submit">
              <Plus className="h-4 w-4" aria-hidden="true" />
            </Button>
          </form>
          {hasInvalidKey ? (
            <p className="text-xs text-destructive" role="alert">
              Label keys must start with a letter and use letters, numbers, periods, underscores,
              or hyphens.
            </p>
          ) : null}
          {reservedDraftBlocked ? (
            <p className="text-xs text-destructive" role="alert">
              Reserved label keys require a superadmin or service account.
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
