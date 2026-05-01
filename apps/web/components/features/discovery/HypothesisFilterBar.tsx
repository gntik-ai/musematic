"use client";

import { Select } from "@/components/ui/select";

export interface HypothesisFilterState {
  state: string;
  confidence: string;
  sort: "elo_desc" | "created_at";
}

export function HypothesisFilterBar({
  value,
  onChange,
}: {
  value: HypothesisFilterState;
  onChange: (value: HypothesisFilterState) => void;
}) {
  return (
    <div className="grid gap-3 rounded-lg border border-border bg-card p-3 md:grid-cols-3">
      <label className="grid gap-1 text-sm">
        <span className="font-medium">State</span>
        <Select
          value={value.state}
          onChange={(event) => onChange({ ...value, state: event.target.value })}
        >
          <option value="">All states</option>
          <option value="active">Proposed / active</option>
          <option value="merged">Confirmed / merged</option>
          <option value="retired">Refuted / retired</option>
        </Select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium">Confidence</span>
        <Select
          value={value.confidence}
          onChange={(event) => onChange({ ...value, confidence: event.target.value })}
        >
          <option value="">All tiers</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </Select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium">Sort</span>
        <Select
          value={value.sort}
          onChange={(event) =>
            onChange({ ...value, sort: event.target.value as HypothesisFilterState["sort"] })
          }
        >
          <option value="elo_desc">Ranking</option>
          <option value="created_at">Created</option>
        </Select>
      </label>
    </div>
  );
}
