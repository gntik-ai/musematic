"use client";

import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { AGENT_ROLE_TYPES, type AgentRoleType } from "@/lib/types/agent-management";
import { toTitleCase } from "@/lib/utils";

export interface RoleTypeSelectorProps {
  value: AgentRoleType;
  customRole?: string;
  onValueChange: (type: AgentRoleType, customRole?: string) => void;
  disabled?: boolean;
}

export function RoleTypeSelector({
  value,
  customRole = "",
  onValueChange,
  disabled = false,
}: RoleTypeSelectorProps) {
  return (
    <div className="space-y-4">
      <label className="space-y-2 text-sm">
        <span className="font-medium">Role type</span>
        <Select
          disabled={disabled}
          value={value}
          onChange={(event) => onValueChange(event.target.value as AgentRoleType, customRole)}
        >
          {AGENT_ROLE_TYPES.map((option) => (
            <option key={option} value={option}>
              {toTitleCase(option)}
            </option>
          ))}
        </Select>
      </label>
      {value === "custom" ? (
        <label className="space-y-2 text-sm">
          <span className="font-medium">Custom role</span>
          <Input
            disabled={disabled}
            placeholder="Describe the custom role"
            value={customRole}
            onChange={(event) => onValueChange("custom", event.target.value)}
          />
        </label>
      ) : null}
    </div>
  );
}
