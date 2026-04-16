"use client";

import { useWorkspaceStore } from "@/store/workspace-store";
import { useNamespaces } from "@/lib/hooks/use-namespaces";
import { buildAgentFqn } from "@/lib/types/agent-management";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

export interface FQNInputProps {
  namespace: string;
  localName: string;
  onNamespaceChange: (namespace: string) => void;
  onLocalNameChange: (localName: string) => void;
  disabled?: boolean;
}

export function FQNInput({
  namespace,
  localName,
  onNamespaceChange,
  onLocalNameChange,
  disabled = false,
}: FQNInputProps) {
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const namespacesQuery = useNamespaces(workspaceId);

  return (
    <div className="grid gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
      <label className="space-y-2 text-sm">
        <span className="font-medium">Namespace</span>
        <Select
          aria-label="Namespace"
          disabled={disabled}
          value={namespace}
          onChange={(event) => onNamespaceChange(event.target.value)}
        >
          <option value="">Select namespace</option>
          {(namespacesQuery.data ?? []).map((entry) => (
            <option key={entry.namespace} value={entry.namespace}>
              {entry.namespace}
            </option>
          ))}
        </Select>
      </label>
      <label className="space-y-2 text-sm">
        <span className="font-medium">Local name</span>
        <Input
          aria-label="Local name"
          disabled={disabled}
          pattern="^[a-z0-9-]+$"
          placeholder="agent-local-name"
          value={localName}
          onChange={(event) => onLocalNameChange(event.target.value)}
        />
        <p className="text-xs text-muted-foreground">
          Preview: {buildAgentFqn(namespace || "namespace", localName || "local-name")}
        </p>
      </label>
    </div>
  );
}
