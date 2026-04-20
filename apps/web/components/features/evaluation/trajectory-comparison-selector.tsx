"use client";

import { Select } from "@/components/ui/select";
import type { TrajectoryComparisonMethod } from "@/types/evaluation";

const DESCRIPTIONS: Record<TrajectoryComparisonMethod, string> = {
  exact_match: "Strictly compare generated outputs against the benchmark response.",
  semantic_similarity: "Use semantic closeness when exact wording should not dominate the score.",
  edit_distance: "Track output drift with string-level edit distance for deterministic checks.",
  trajectory_judge: "Use an LLM judge to compare the full reasoning trajectory instead of only the final answer.",
};

export interface TrajectoryComparisonSelectorProps {
  value: TrajectoryComparisonMethod;
  onChange: (value: TrajectoryComparisonMethod) => void;
}

export function TrajectoryComparisonSelector({ value, onChange }: TrajectoryComparisonSelectorProps) {
  return (
    <div className="space-y-3">
      <label className="text-sm font-medium text-foreground" htmlFor="trajectory-comparison-method">
        Comparison method
      </label>
      <Select
        id="trajectory-comparison-method"
        value={value}
        onChange={(event) => onChange(event.target.value as TrajectoryComparisonMethod)}
      >
        <option value="exact_match">Exact match</option>
        <option value="semantic_similarity">Semantic similarity</option>
        <option value="edit_distance">Edit distance</option>
        <option value="trajectory_judge">Trajectory judge</option>
      </Select>
      <p className="text-sm text-muted-foreground">{DESCRIPTIONS[value]}</p>
    </div>
  );
}
