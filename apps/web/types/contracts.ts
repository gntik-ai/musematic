export interface AgentContract {
  id: string;
  version: string;
  status: "active" | "superseded";
  publishedAt: string;
  supersededAt: string | null;
  signatories: string[];
  documentExcerpt: string;
}

export interface A2AAgentCard {
  card: Record<string, unknown>;
  lastPublishedAt: string | null;
}

export interface McpServerRegistration {
  id: string;
  name: string;
  endpoint: string;
  capabilityCounts: { tools: number; resources: number };
  healthStatus: "healthy" | "unhealthy" | "unknown";
  lastHealthCheckAt: string | null;
}
