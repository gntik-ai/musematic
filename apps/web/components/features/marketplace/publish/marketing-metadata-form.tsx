"use client";

/**
 * UPD-049 — Marketing metadata form rendered when the user picks the
 * `public_default_tenant` scope. Validates against the same constraints
 * as the backend Pydantic schema (`MarketingMetadata`):
 *
 * - `category` MUST be one of `MARKETING_CATEGORIES`.
 * - `marketing_description` MUST be 20–500 characters.
 * - `tags` MUST have between 1 and 10 entries (lowercased + trimmed).
 *
 * The form is uncontrolled at the input level but emits its full state
 * via `onChange` on every keystroke so the parent publish flow can
 * persist a draft if needed.
 */

import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import {
  MARKETING_CATEGORIES,
  MARKETING_CATEGORY_LABELS,
  type MarketingCategory,
} from "@/lib/marketplace/categories";
import type { MarketingMetadata } from "@/lib/marketplace/types";

const DESCRIPTION_MIN = 20;
const DESCRIPTION_MAX = 500;
const TAG_MAX = 10;

export interface MarketingMetadataFormProps {
  value: MarketingMetadata;
  onChange: (next: MarketingMetadata) => void;
  /** When true the parent has attempted to submit — show validation errors. */
  showErrors?: boolean;
}

export function MarketingMetadataForm({
  value,
  onChange,
  showErrors = false,
}: MarketingMetadataFormProps) {
  const [tagInput, setTagInput] = useState("");

  const categoryError = !value.category
    ? "Pick a category."
    : !MARKETING_CATEGORIES.includes(value.category)
    ? "Pick a category from the list."
    : null;

  const descriptionError = useMemo(() => {
    const len = value.marketing_description.trim().length;
    if (len < DESCRIPTION_MIN) {
      return `Description must be at least ${DESCRIPTION_MIN} characters.`;
    }
    if (len > DESCRIPTION_MAX) {
      return `Description must be at most ${DESCRIPTION_MAX} characters.`;
    }
    return null;
  }, [value.marketing_description]);

  const tagsError =
    value.tags.length === 0
      ? "Add at least one tag."
      : value.tags.length > TAG_MAX
      ? `At most ${TAG_MAX} tags.`
      : null;

  const addTag = () => {
    const next = tagInput.trim().toLowerCase();
    if (!next) return;
    if (value.tags.includes(next)) {
      setTagInput("");
      return;
    }
    if (value.tags.length >= TAG_MAX) return;
    onChange({ ...value, tags: [...value.tags, next] });
    setTagInput("");
  };

  const removeTag = (tag: string) => {
    onChange({ ...value, tags: value.tags.filter((t) => t !== tag) });
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="marketing-category">Category</Label>
        <Select
          id="marketing-category"
          data-testid="marketing-category"
          value={value.category || ""}
          onChange={(event) =>
            onChange({
              ...value,
              category: event.target.value as MarketingCategory,
            })
          }
        >
          <option value="" disabled>
            Pick a category
          </option>
          {MARKETING_CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {MARKETING_CATEGORY_LABELS[category]}
            </option>
          ))}
        </Select>
        {showErrors && categoryError ? (
          <p className="text-sm text-destructive">{categoryError}</p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="marketing-description">Description</Label>
        <Textarea
          id="marketing-description"
          rows={4}
          maxLength={DESCRIPTION_MAX + 100} /* hard stop above the validator */
          value={value.marketing_description}
          onChange={(event) =>
            onChange({ ...value, marketing_description: event.target.value })
          }
          placeholder="Tell potential users what this agent does and when to use it."
        />
        <p className="text-xs text-muted-foreground">
          {value.marketing_description.trim().length}/{DESCRIPTION_MAX} characters
        </p>
        {showErrors && descriptionError ? (
          <p className="text-sm text-destructive">{descriptionError}</p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="marketing-tags">Tags</Label>
        <div className="flex flex-wrap items-center gap-2">
          {value.tags.map((tag) => (
            <Badge key={tag} variant="secondary" className="gap-1">
              {tag}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-4 w-4 p-0"
                aria-label={`Remove tag ${tag}`}
                onClick={() => removeTag(tag)}
              >
                <X className="h-3 w-3" />
              </Button>
            </Badge>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            id="marketing-tags"
            value={tagInput}
            onChange={(event) => setTagInput(event.target.value)}
            placeholder="Type a tag and press Enter"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addTag();
              }
            }}
          />
          <Button
            type="button"
            variant="outline"
            onClick={addTag}
            disabled={!tagInput.trim() || value.tags.length >= TAG_MAX}
          >
            Add
          </Button>
        </div>
        {showErrors && tagsError ? (
          <p className="text-sm text-destructive">{tagsError}</p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Returns true when the metadata satisfies all backend-mirrored constraints.
 * Use this in the parent publish flow to gate the Submit button.
 */
export function isMarketingMetadataValid(metadata: MarketingMetadata): boolean {
  if (!metadata.category) return false;
  if (!MARKETING_CATEGORIES.includes(metadata.category)) return false;
  const len = metadata.marketing_description.trim().length;
  if (len < DESCRIPTION_MIN || len > DESCRIPTION_MAX) return false;
  if (metadata.tags.length === 0 || metadata.tags.length > TAG_MAX) return false;
  return true;
}
