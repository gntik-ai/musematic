import type { FqnPattern } from "@/types/fqn";

const FQN_PATTERN_REGEX =
  /^(?:(?<scope>[a-z0-9_-]+):(?<target>[a-z0-9_*:-]+)|(?<bare>[a-z0-9_*:-]+))$/i;

export function isValidFqnPattern(pattern: string): boolean {
  return FQN_PATTERN_REGEX.test(pattern.trim());
}

export function describeAudience(pattern: FqnPattern): string {
  const value = pattern.trim();
  if (!value) {
    return "No audience selected";
  }
  if (value === "workspace:*/agent:*") {
    return "All workspaces, all agents";
  }
  const [namespace, localName] = value.split(":", 2);
  if (namespace == "*" || namespace === "workspace:*") {
    return "All workspaces";
  }
  if (localName === "*" || value.endsWith(":*")) {
    return `All agents in ${namespace}`;
  }
  if (value.includes("*")) {
    return `Agents matching ${value}`;
  }
  return `Only ${value}`;
}
