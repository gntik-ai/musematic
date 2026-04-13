import { http, HttpResponse } from "msw";
import type {
  WorkflowDefinitionResponse,
  WorkflowSchema,
  WorkflowVersionResponse,
} from "@/types/workflows";

function createWorkflowYaml(name: string): string {
  return [
    `name: ${name}`,
    "version: 1.0.0",
    "triggers:",
    "  - type: manual",
    "steps:",
    "  collect_context:",
    "    type: agent_task",
    "    agent_fqn: operations/context-loader",
    "  evaluate_risk:",
    "    type: agent_task",
    "    agent_fqn: trust/risk-evaluator",
    "    dependencies: [collect_context]",
    "  approval_gate:",
    "    type: approval_gate",
    "    dependencies: [evaluate_risk]",
    "  finalize_case:",
    "    type: agent_task",
    "    agent_fqn: operations/case-writer",
    "    dependencies: [approval_gate]",
  ].join("\n");
}

function buildCompiledIrResponse(name: string) {
  return {
    metadata: {
      name,
      description: `${name} orchestration flow`,
      version: "1.0.0",
      default_reasoning_mode: "direct" as const,
      default_context_budget: {
        max_tokens: 6000,
        max_rounds: 3,
        max_cost_usd: 1.25,
      },
    },
    triggers: [{ type: "manual" as const, config: {} }],
    steps: [
      {
        id: "collect_context",
        name: "Collect Context",
        type: "agent_task" as const,
        agent_fqn: "operations/context-loader",
        dependencies: [],
      },
      {
        id: "evaluate_risk",
        name: "Evaluate Risk",
        type: "agent_task" as const,
        agent_fqn: "trust/risk-evaluator",
        dependencies: ["collect_context"],
        reasoning_mode: "tree_of_thought" as const,
      },
      {
        id: "approval_gate",
        name: "Approval Gate",
        type: "approval_gate" as const,
        dependencies: ["evaluate_risk"],
        approval_config: {
          approver_role: "workspace_admin",
          timeout_seconds: 900,
        },
      },
      {
        id: "finalize_case",
        name: "Finalize Case",
        type: "agent_task" as const,
        agent_fqn: "operations/case-writer",
        dependencies: ["approval_gate"],
      },
    ],
  };
}

function buildWorkflowDefinition(
  id: string,
  workspaceId: string,
  name: string,
  versionNumber: number,
): WorkflowDefinitionResponse {
  const timestamp = new Date("2026-04-13T08:00:00.000Z").toISOString();

  return {
    id,
    workspace_id: workspaceId,
    name,
    description: `${name} managed in Workflow Studio`,
    current_version_id: `${id}-version-${versionNumber}`,
    current_version_number: versionNumber,
    status: "active",
    created_at: timestamp,
    updated_at: timestamp,
  };
}

function buildWorkflowVersion(
  workflowId: string,
  versionNumber: number,
  name: string,
): WorkflowVersionResponse {
  return {
    id: `${workflowId}-version-${versionNumber}`,
    workflow_id: workflowId,
    version_number: versionNumber,
    yaml_content: createWorkflowYaml(name),
    compiled_ir: buildCompiledIrResponse(name),
    created_at: new Date("2026-04-13T08:00:00.000Z").toISOString(),
    created_by: "user-1",
  };
}

function createWorkflowSchema(): WorkflowSchema {
  return {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    type: "object",
    required: ["name", "steps"],
    properties: {
      name: { type: "string" },
      version: { type: "string" },
      triggers: {
        type: "array",
        items: {
          type: "object",
          required: ["type"],
          properties: {
            type: { type: "string" },
            config: { type: "object" },
          },
        },
      },
      steps: {
        type: "object",
        additionalProperties: {
          type: "object",
          required: ["type"],
          properties: {
            type: { type: "string" },
            agent_fqn: { type: "string" },
            dependencies: {
              type: "array",
              items: { type: "string" },
            },
          },
        },
      },
    },
  };
}

export interface WorkflowMockState {
  definitions: WorkflowDefinitionResponse[];
  versionsByWorkflowId: Record<string, WorkflowVersionResponse[]>;
  schema: WorkflowSchema;
}

export function createWorkflowMockState(): WorkflowMockState {
  const definitions = [
    buildWorkflowDefinition("workflow-1", "workspace-1", "KYC Onboarding", 2),
    buildWorkflowDefinition("workflow-2", "workspace-1", "Campaign Health", 1),
    buildWorkflowDefinition("workflow-3", "workspace-2", "Incident Escalation", 1),
  ];

  return {
    definitions,
    versionsByWorkflowId: {
      "workflow-1": [
        buildWorkflowVersion("workflow-1", 1, "KYC Onboarding"),
        buildWorkflowVersion("workflow-1", 2, "KYC Onboarding"),
      ],
      "workflow-2": [buildWorkflowVersion("workflow-2", 1, "Campaign Health")],
      "workflow-3": [
        buildWorkflowVersion("workflow-3", 1, "Incident Escalation"),
      ],
    },
    schema: createWorkflowSchema(),
  };
}

export const workflowFixtures: WorkflowMockState = createWorkflowMockState();

export function resetWorkflowFixtures(): void {
  const fresh = createWorkflowMockState();
  workflowFixtures.definitions = fresh.definitions;
  workflowFixtures.versionsByWorkflowId = fresh.versionsByWorkflowId;
  workflowFixtures.schema = fresh.schema;
}

export const workflowHandlers = [
  http.get("*/api/v1/workflows", ({ request }) => {
    const url = new URL(request.url);
    const workspaceId = url.searchParams.get("workspace_id");
    const cursor = Number(url.searchParams.get("cursor") ?? "0");
    const limit = Number(url.searchParams.get("limit") ?? "20");
    const filtered = workflowFixtures.definitions.filter(
      (definition) => !workspaceId || definition.workspace_id === workspaceId,
    );
    const items = filtered.slice(cursor, cursor + limit);
    const nextCursor =
      cursor + items.length < filtered.length ? String(cursor + items.length) : null;

    return HttpResponse.json({
      items,
      next_cursor: nextCursor,
      total: filtered.length,
    });
  }),
  http.get("*/api/v1/workflows/schema", () =>
    HttpResponse.json(workflowFixtures.schema),
  ),
  http.get("*/api/v1/workflows/:workflowId", ({ params }) => {
    const workflowId = String(params.workflowId);
    const workflow = workflowFixtures.definitions.find(
      (definition) => definition.id === workflowId,
    );

    if (!workflow) {
      return HttpResponse.json(
        { code: "NOT_FOUND", message: "Workflow not found", details: {} },
        { status: 404 },
      );
    }

    return HttpResponse.json(workflow);
  }),
  http.get("*/api/v1/workflows/:workflowId/versions/:versionId", ({ params }) => {
    const workflowId = String(params.workflowId);
    const versionId = String(params.versionId);
    const version = workflowFixtures.versionsByWorkflowId[workflowId]?.find(
      (entry) => entry.id === versionId,
    );

    if (!version) {
      return HttpResponse.json(
        { code: "NOT_FOUND", message: "Workflow version not found", details: {} },
        { status: 404 },
      );
    }

    return HttpResponse.json(version);
  }),
  http.post("*/api/v1/workflows", async ({ request }) => {
    const body = (await request.json()) as {
      workspace_id: string;
      name: string;
      description?: string | null;
      yaml_content: string;
    };
    const nextId = `workflow-${workflowFixtures.definitions.length + 1}`;
    const definition = {
      ...buildWorkflowDefinition(nextId, body.workspace_id, body.name, 1),
      description: body.description ?? null,
    };
    const version: WorkflowVersionResponse = {
      id: `${nextId}-version-1`,
      workflow_id: nextId,
      version_number: 1,
      yaml_content: body.yaml_content,
      compiled_ir: buildCompiledIrResponse(body.name),
      created_at: new Date().toISOString(),
      created_by: "user-1",
    };

    workflowFixtures.definitions = [...workflowFixtures.definitions, definition];
    workflowFixtures.versionsByWorkflowId[nextId] = [version];

    return HttpResponse.json(definition, { status: 201 });
  }),
  http.patch("*/api/v1/workflows/:workflowId", async ({ params, request }) => {
    const workflowId = String(params.workflowId);
    const body = (await request.json()) as {
      yaml_content: string;
      description?: string | null;
    };
    const currentDefinition = workflowFixtures.definitions.find(
      (definition) => definition.id === workflowId,
    );

    if (!currentDefinition) {
      return HttpResponse.json(
        { code: "NOT_FOUND", message: "Workflow not found", details: {} },
        { status: 404 },
      );
    }

    const nextVersionNumber = currentDefinition.current_version_number + 1;
    const nextVersion = {
      id: `${workflowId}-version-${nextVersionNumber}`,
      workflow_id: workflowId,
      version_number: nextVersionNumber,
      yaml_content: body.yaml_content,
      compiled_ir: buildCompiledIrResponse(currentDefinition.name),
      created_at: new Date().toISOString(),
      created_by: "user-1",
    } satisfies WorkflowVersionResponse;

    workflowFixtures.versionsByWorkflowId[workflowId] = [
      ...(workflowFixtures.versionsByWorkflowId[workflowId] ?? []),
      nextVersion,
    ];
    workflowFixtures.definitions = workflowFixtures.definitions.map((definition) =>
      definition.id === workflowId
        ? {
            ...definition,
            current_version_id: nextVersion.id,
            current_version_number: nextVersionNumber,
            description: body.description ?? definition.description,
            updated_at: new Date().toISOString(),
          }
        : definition,
    );

    return HttpResponse.json(
      workflowFixtures.definitions.find((definition) => definition.id === workflowId),
    );
  }),
];
