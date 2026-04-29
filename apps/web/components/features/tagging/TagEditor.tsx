"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { TaggableEntityType } from "@/lib/api/tagging";
import { useEntityTags, useTagAttach, useTagDetach } from "@/lib/api/tagging";
import { Plus, Tag, X } from "lucide-react";
import type { FormEvent } from "react";
import { useMemo, useState } from "react";

const TAG_PATTERN = /^[a-zA-Z0-9._-]+$/;
const MAX_TAGS_PER_ENTITY = 50;

interface TagEditorProps {
  entityType: TaggableEntityType;
  entityId: string;
  readOnly?: boolean;
}

export function TagEditor({ entityType, entityId, readOnly = false }: TagEditorProps) {
  const [draft, setDraft] = useState("");
  const { data } = useEntityTags(entityType, entityId);
  const attach = useTagAttach(entityType, entityId);
  const detach = useTagDetach(entityType, entityId);
  const tags = data?.tags ?? [];
  const normalized = draft.trim();
  const isAtLimit = tags.length >= MAX_TAGS_PER_ENTITY;
  const canSubmit = useMemo(
    () => normalized.length > 0 && TAG_PATTERN.test(normalized) && !isAtLimit && !readOnly,
    [isAtLimit, normalized, readOnly],
  );

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    await attach.mutateAsync(normalized);
    setDraft("");
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {tags.map((item) => (
          <span
            key={item.tag}
            className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-2 text-sm"
          >
            <Tag className="h-3.5 w-3.5" aria-hidden="true" />
            {item.tag}
            {!readOnly ? (
              <Button
                aria-label={`Remove ${item.tag}`}
                className="h-6 w-6"
                onClick={() => detach.mutate(item.tag)}
                size="icon"
                variant="ghost"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            ) : null}
          </span>
        ))}
      </div>
      {!readOnly ? (
        <form className="flex gap-2" onSubmit={onSubmit}>
          <Input
            aria-label="Tag"
            className="max-w-64"
            disabled={isAtLimit}
            maxLength={128}
            onChange={(event) => setDraft(event.target.value)}
            value={draft}
          />
          <Button aria-label="Add tag" disabled={!canSubmit} size="icon" type="submit">
            <Plus className="h-4 w-4" aria-hidden="true" />
          </Button>
        </form>
      ) : null}
    </div>
  );
}
