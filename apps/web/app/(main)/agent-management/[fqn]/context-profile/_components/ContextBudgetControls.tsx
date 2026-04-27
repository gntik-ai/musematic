"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ContextBudgetControls() {
  return (
    <div className="grid gap-4 rounded-lg border p-4 sm:grid-cols-2">
      <div className="space-y-2">
        <Label htmlFor="max-tokens">Max tokens</Label>
        <Input id="max-tokens" min={1} type="number" value={8192} readOnly />
      </div>
      <div className="space-y-2">
        <Label htmlFor="max-documents">Max documents</Label>
        <Input id="max-documents" min={1} type="number" value={50} readOnly />
      </div>
    </div>
  );
}

