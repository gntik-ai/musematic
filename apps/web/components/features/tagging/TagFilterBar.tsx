"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tag, X } from "lucide-react";
import { useMemo, useState } from "react";

interface TagFilterBarProps {
  value: string[];
  onChange: (nextTags: string[]) => void;
}

export function TagFilterBar({ value, onChange }: TagFilterBarProps) {
  const [draft, setDraft] = useState("");
  const normalized = draft.trim();
  const tags = useMemo(() => Array.from(new Set(value.map((item) => item.trim()).filter(Boolean))), [value]);

  function addTag() {
    if (!normalized) {
      return;
    }
    onChange(Array.from(new Set([...tags, normalized])));
    setDraft("");
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {tags.map((tag) => (
        <Button
          className="h-8 gap-1 px-2"
          key={tag}
          onClick={() => onChange(tags.filter((item) => item !== tag))}
          variant="outline"
        >
          <Tag className="h-3.5 w-3.5" aria-hidden="true" />
          {tag}
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      ))}
      <Input
        aria-label="Tag filter"
        className="h-8 w-40"
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            addTag();
          }
        }}
        value={draft}
      />
    </div>
  );
}
