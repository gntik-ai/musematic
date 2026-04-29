"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Filter, Plus, X } from "lucide-react";
import { useState } from "react";

interface LabelFilterPopoverProps {
  value: Record<string, string>;
  onChange: (nextLabels: Record<string, string>) => void;
}

export function LabelFilterPopover({ value, onChange }: LabelFilterPopoverProps) {
  const [key, setKey] = useState("");
  const [labelValue, setLabelValue] = useState("");

  function addFilter() {
    const normalizedKey = key.trim();
    if (!normalizedKey) {
      return;
    }
    onChange({ ...value, [normalizedKey]: labelValue.trim() });
    setKey("");
    setLabelValue("");
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button aria-label="Label filters" size="icon" variant="outline">
          <Filter className="h-4 w-4" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 space-y-3">
        <div className="grid gap-2">
          {Object.entries(value).map(([itemKey, itemValue]) => (
            <div className="grid grid-cols-[1fr_1fr_auto] items-center gap-2 text-sm" key={itemKey}>
              <span className="font-medium">{itemKey}</span>
              <span className="text-muted-foreground">{itemValue}</span>
              <Button
                aria-label={`Remove ${itemKey}`}
                className="h-7 w-7"
                onClick={() => {
                  const next = { ...value };
                  delete next[itemKey];
                  onChange(next);
                }}
                size="icon"
                variant="ghost"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-[1fr_1fr_auto] gap-2">
          <Input aria-label="Label filter key" onChange={(event) => setKey(event.target.value)} value={key} />
          <Input aria-label="Label filter value" onChange={(event) => setLabelValue(event.target.value)} value={labelValue} />
          <Button aria-label="Add label filter" onClick={addFilter} size="icon">
            <Plus className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
