"use client";

import { Select } from "@/components/ui/select";

interface Snapshot {
  id: string;
  label: string;
}

interface CycleSnapshotSelectorProps {
  snapshots: Snapshot[];
  value: string;
  onChange: (value: string) => void;
}

export function CycleSnapshotSelector({
  snapshots,
  value,
  onChange,
}: CycleSnapshotSelectorProps) {
  return (
    <Select
      aria-label="Cycle snapshot"
      className="w-full rounded-2xl md:w-[260px]"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      {snapshots.map((snapshot) => (
        <option key={snapshot.id} value={snapshot.id}>
          {snapshot.label}
        </option>
      ))}
    </Select>
  );
}
