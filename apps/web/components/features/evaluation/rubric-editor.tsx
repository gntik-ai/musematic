"use client";

import { memo, useEffect, useMemo, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useRubricEditor } from "@/lib/hooks/use-rubric-editor";
import {
  RUBRIC_WEIGHT_VALIDATION_DEBOUNCE_MS,
  validateWeightSum,
} from "@/lib/validators/rubric-weights";
import { useAuthStore } from "@/store/auth-store";
import { cn } from "@/lib/utils";
import type { RubricDimension } from "@/types/evaluation";

const ADMIN_ROLES = new Set(["workspace_admin", "platform_admin", "superadmin"]);

interface WeightRowProps {
  dimension: RubricDimension;
  onChange: (next: RubricDimension) => void;
  onRemove: () => void;
  disableRemove: boolean;
}

const WeightRow = memo(function WeightRow({
  dimension,
  onChange,
  onRemove,
  disableRemove,
}: WeightRowProps) {
  return (
    <div className="grid gap-3 rounded-2xl border border-border/70 bg-background/70 p-4 md:grid-cols-[1fr,1.4fr,120px,auto]">
      <Input
        aria-label={`Dimension name ${dimension.id}`}
        placeholder="Accuracy"
        value={dimension.name}
        onChange={(event) => onChange({ ...dimension, name: event.target.value })}
      />
      <Input
        aria-label={`Dimension description ${dimension.id}`}
        placeholder="Describe what this dimension measures"
        value={dimension.description}
        onChange={(event) => onChange({ ...dimension, description: event.target.value })}
      />
      <Input
        aria-label={`Dimension weight ${dimension.id}`}
        inputMode="decimal"
        min={0}
        step="0.05"
        type="number"
        value={dimension.weight}
        onChange={(event) =>
          onChange({
            ...dimension,
            weight: Number(event.target.value || 0),
          })
        }
      />
      <Button
        aria-label={`Remove ${dimension.name || dimension.id}`}
        disabled={disableRemove}
        size="icon"
        type="button"
        variant="ghost"
        onClick={onRemove}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
});

export interface RubricEditorProps {
  suiteId: string;
}

export function RubricEditor({ suiteId }: RubricEditorProps) {
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const canEdit = roles.some((role) => ADMIN_ROLES.has(role));
  const { rubric, isLoading, saveRubric } = useRubricEditor(suiteId);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [dimensions, setDimensions] = useState<RubricDimension[]>([]);
  const [validation, setValidation] = useState({ sum: 0, isValid: false });

  useEffect(() => {
    if (!rubric) {
      return;
    }
    setName(rubric.name);
    setDescription(rubric.description);
    setDimensions(rubric.dimensions);
  }, [rubric]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setValidation(validateWeightSum(dimensions));
    }, RUBRIC_WEIGHT_VALIDATION_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [dimensions]);

  const isSaveDisabled = useMemo(() => {
    if (!canEdit) {
      return true;
    }
    if (saveRubric.isPending) {
      return true;
    }
    if (!name.trim()) {
      return true;
    }
    if (dimensions.length === 0) {
      return true;
    }
    if (!validation.isValid) {
      return true;
    }
    return dimensions.some((dimension) => !dimension.name.trim() || !dimension.description.trim());
  }, [canEdit, dimensions, name, saveRubric.isPending, validation.isValid]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Rubric editor</CardTitle>
        <CardDescription>
          Define the scoring dimensions used by the judge and keep their weights balanced.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!canEdit ? (
          <p className="rounded-xl border border-border/70 bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
            Editing rubric weights requires the workspace_admin role.
          </p>
        ) : null}
        <div className="grid gap-4 md:grid-cols-2">
          <Input
            aria-label="Rubric name"
            disabled={!canEdit || isLoading}
            placeholder="Trajectory quality rubric"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Textarea
            aria-label="Rubric description"
            disabled={!canEdit || isLoading}
            placeholder="Explain how reviewers should interpret the rubric."
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
        <div className="space-y-3">
          {dimensions.map((dimension, index) => (
            <WeightRow
              key={dimension.id}
              dimension={dimension}
              disableRemove={dimensions.length === 1 || !canEdit}
              onChange={(next) => {
                setDimensions((current) =>
                  current.map((item, itemIndex) => (itemIndex === index ? next : item)),
                );
              }}
              onRemove={() => {
                setDimensions((current) => current.filter((_, itemIndex) => itemIndex !== index));
              }}
            />
          ))}
          <Button
            disabled={!canEdit}
            type="button"
            variant="outline"
            onClick={() => {
              setDimensions((current) => [
                ...current,
                {
                  id: `dimension-${current.length + 1}`,
                  name: "",
                  description: "",
                  weight: 0,
                  scaleType: "numeric_1_5",
                  categoricalValues: null,
                },
              ]);
            }}
          >
            <Plus className="h-4 w-4" />
            Add dimension
          </Button>
        </div>
        <div
          className={cn(
            "rounded-xl border px-4 py-3 text-sm font-medium",
            validation.isValid
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700"
              : "border-red-500/40 bg-red-500/10 text-red-700",
          )}
        >
          Weight sum: {validation.sum.toFixed(2)} {validation.isValid ? "(valid)" : "(must equal 1.00)"}
        </div>
        <div className="flex justify-end">
          <Button
            disabled={isSaveDisabled}
            onClick={() =>
              void saveRubric.mutateAsync({
                name: name.trim(),
                description: description.trim(),
                dimensions,
                comparisonMethod: rubric?.comparisonMethod ?? "exact_match",
              })
            }
          >
            Save rubric
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
