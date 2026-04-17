"use client";

import type {
  AgentMetadataUpdateRequest,
  CompositionBlueprint,
  CompositionWizardCustomizations,
} from "@/lib/types/agent-management";

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

function titleize(value: string): string {
  return value
    .split("-")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function resolveDescriptionSnippet(description: string): string {
  const trimmed = description.trim();
  if (trimmed.length <= 160) {
    return trimmed;
  }

  return `${trimmed.slice(0, 157).trimEnd()}...`;
}

export function buildDraftMetadataFromBlueprint({
  blueprint,
  customizations,
  description,
  workspaceSlug,
}: {
  blueprint: CompositionBlueprint;
  customizations: Partial<CompositionWizardCustomizations>;
  description: string;
  workspaceSlug: string | null;
}): AgentMetadataUpdateRequest {
  const namespace = slugify(workspaceSlug ?? "workspace") || "workspace";
  const localName =
    slugify(
      description
        .split(/\s+/)
        .slice(0, 6)
        .join(" "),
    ) || "generated-agent";
  const toolSelections =
    customizations.tool_selections ?? blueprint.tool_selections.value;
  const connectorSuggestions =
    customizations.connector_suggestions ?? blueprint.connector_suggestions.value;
  return {
    namespace,
    local_name: localName,
    name: titleize(localName),
    description: resolveDescriptionSnippet(description),
    purpose: description.trim(),
    approach: "Generated from the composition wizard blueprint.",
    tags: Array.from(new Set([...toolSelections, ...connectorSuggestions])).slice(0, 6),
    category: "ai-composed",
    maturity_level: "experimental",
    role_type: "executor",
    custom_role: null,
    reasoning_modes: ["deterministic"],
    visibility_patterns: [
      {
        pattern: `${namespace}:*`,
        description: "Visible inside the current workspace namespace.",
      },
    ],
  };
}
