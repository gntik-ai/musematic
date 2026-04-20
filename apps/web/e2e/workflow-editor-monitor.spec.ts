import { expect, test, type Page } from "@playwright/test";

declare global {
  interface Window {
    __emitWsEvent?: (message: Record<string, unknown>) => void;
  }
}

const workflowYaml = [
  "name: KYC Onboarding",
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

function buildWorkflowDefinition(id: string, name: string, versionNumber: number) {
  return {
    id,
    workspace_id: "workspace-1",
    name,
    description: `${name} managed in Workflow Studio`,
    current_version_id: `${id}-version-${versionNumber}`,
    current_version_number: versionNumber,
    status: "active",
    created_at: "2026-04-13T08:00:00.000Z",
    updated_at: "2026-04-13T08:00:00.000Z",
  };
}

function buildWorkflowVersion(workflowId: string, name: string) {
  return {
    id: `${workflowId}-version-1`,
    workflow_id: workflowId,
    version_number: 1,
    yaml_content: workflowYaml,
    compiled_ir: {
      metadata: {
        name,
        description: `${name} orchestration flow`,
        version: "1.0.0",
        default_reasoning_mode: "direct",
        default_context_budget: {
          max_tokens: 6000,
          max_rounds: 3,
          max_cost_usd: 1.25,
        },
      },
      triggers: [{ type: "manual", config: {} }],
      steps: [
        {
          id: "collect_context",
          name: "Collect Context",
          type: "agent_task",
          agent_fqn: "operations/context-loader",
          dependencies: [],
        },
        {
          id: "evaluate_risk",
          name: "Evaluate Risk",
          type: "agent_task",
          agent_fqn: "trust/risk-evaluator",
          dependencies: ["collect_context"],
        },
        {
          id: "approval_gate",
          name: "Approval Gate",
          type: "approval_gate",
          dependencies: ["evaluate_risk"],
        },
        {
          id: "finalize_case",
          name: "Finalize Case",
          type: "agent_task",
          agent_fqn: "operations/case-writer",
          dependencies: ["approval_gate"],
        },
      ],
    },
    created_at: "2026-04-13T08:00:00.000Z",
    created_by: "user-1",
  };
}

function buildExecution(executionId: string, workflowId: string, status: string) {
  return {
    id: executionId,
    workflow_id: workflowId,
    workflow_version_id: `${workflowId}-version-1`,
    workflow_version_number: 1,
    status,
    triggered_by: "user-1",
    correlation_context: {
      workspace_id: "workspace-1",
      execution_id: executionId,
      workflow_id: workflowId,
      conversation_id: "conversation-1",
    },
    started_at: "2026-04-13T09:00:00.000Z",
    completed_at: status === "completed" ? "2026-04-13T09:10:00.000Z" : null,
    failure_reason: null,
  };
}

async function setMonacoEditorValue(page: Page, value: string) {
  await page.waitForFunction(() => {
    const globalWindow = window as Window & {
      monaco?: {
        editor?: {
          getModels(): Array<{ setValue(nextValue: string): void }>;
        };
      };
    };

    return Boolean(globalWindow.monaco?.editor?.getModels().length);
  });

  await page.evaluate((nextValue) => {
    const globalWindow = window as Window & {
      monaco?: {
        editor?: {
          getModels(): Array<{ setValue(value: string): void }>;
        };
      };
    };

    globalWindow.monaco?.editor?.getModels()?.[0]?.setValue(nextValue);
  }, value);
}

async function installWorkspaceState(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem(
      "workspace-storage",
      JSON.stringify({
        state: {
          currentWorkspace: {
            id: "workspace-1",
            name: "Signal Lab",
            slug: "signal-lab",
            description: "Primary operations workspace",
            memberCount: 18,
            createdAt: "2026-04-10T09:00:00.000Z",
          },
          sidebarCollapsed: false,
        },
        version: 0,
      }),
    );
  });
}

async function installAuthState(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem(
      "auth-storage",
      JSON.stringify({
        state: {
          user: {
            id: "4d1b0f76-a961-4f8d-8bcb-3f7d5f530001",
            email: "alex@musematic.dev",
            displayName: "Alex Mercer",
            avatarUrl: null,
            roles: [
              "workspace_admin",
              "agent_operator",
              "analytics_viewer",
            ],
            workspaceId: "workspace-1",
            mfaEnrolled: true,
          },
          accessToken: "mock-access-token",
          refreshToken: "mock-refresh-token",
          isAuthenticated: true,
          isLoading: false,
        },
        version: 0,
      }),
    );
  });
}

async function installMockWebSocket(page: Page) {
  await page.addInitScript(() => {
    const targetUrl = "ws://localhost:8000/ws";
    const NativeWebSocket = window.WebSocket;
    const sockets = new Set<MockExecutionWebSocket>();

    class MockExecutionWebSocket extends EventTarget {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      readonly url = targetUrl;
      readonly protocol = "";
      readonly extensions = "";
      binaryType: BinaryType = "blob";
      bufferedAmount = 0;
      readyState = MockExecutionWebSocket.CONNECTING;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onopen: ((event: Event) => void) | null = null;

      constructor() {
        super();
        sockets.add(this);
        window.setTimeout(() => {
          this.readyState = MockExecutionWebSocket.OPEN;
          this.dispatchSocketEvent(new Event("open"));
        }, 0);
      }

      close() {
        if (this.readyState === MockExecutionWebSocket.CLOSED) {
          return;
        }

        this.readyState = MockExecutionWebSocket.CLOSED;
        this.dispatchSocketEvent(new CloseEvent("close"));
        sockets.delete(this);
      }

      send() {}

      dispatchMessage(message: Record<string, unknown>) {
        this.dispatchSocketEvent(
          new MessageEvent("message", {
            data: JSON.stringify(message),
          }),
        );
      }

      private dispatchSocketEvent(
        event: Event | MessageEvent<string> | CloseEvent,
      ) {
        this.dispatchEvent(event);

        if (event.type === "open") {
          this.onopen?.(event);
        } else if (event.type === "message") {
          this.onmessage?.(event as MessageEvent<string>);
        } else if (event.type === "close") {
          this.onclose?.(event as CloseEvent);
        } else if (event.type === "error") {
          this.onerror?.(event);
        }
      }
    }

    window.WebSocket = new Proxy(NativeWebSocket, {
      construct(Target, args) {
        const [url] = args;
        if (typeof url === "string" && url === targetUrl) {
          return new MockExecutionWebSocket();
        }

        return Reflect.construct(Target, args);
      },
    }) as typeof WebSocket;

    window.__emitWsEvent = (message) => {
      sockets.forEach((socket) => socket.dispatchMessage(message));
    };
  });
}

async function mockWorkflowEditorMonitorApi(page: Page) {
  let workflowDefinition = buildWorkflowDefinition("workflow-1", "KYC Onboarding", 1);
  let workflowVersion = buildWorkflowVersion("workflow-1", "KYC Onboarding");
  let execution = buildExecution("execution-1", "workflow-new", "running");
  let executionState = {
    execution_id: "execution-1",
    status: "running",
    completed_step_ids: ["collect_context"],
    active_step_ids: ["evaluate_risk"],
    pending_step_ids: ["approval_gate", "finalize_case"],
    failed_step_ids: [],
    skipped_step_ids: [],
    waiting_for_approval_step_ids: [],
    step_results: {
      collect_context: {
        step_id: "collect_context",
        status: "completed",
        started_at: "2026-04-13T09:00:00.000Z",
        completed_at: "2026-04-13T09:02:00.000Z",
        duration_ms: 120000,
        error: null,
        retry_count: 0,
      },
      evaluate_risk: {
        step_id: "evaluate_risk",
        status: "running",
        started_at: "2026-04-13T09:02:00.000Z",
        completed_at: null,
        duration_ms: null,
        error: null,
        retry_count: 0,
      },
      approval_gate: {
        step_id: "approval_gate",
        status: "pending",
        started_at: null,
        completed_at: null,
        duration_ms: null,
        error: null,
        retry_count: 0,
      },
      finalize_case: {
        step_id: "finalize_case",
        status: "pending",
        started_at: null,
        completed_at: null,
        duration_ms: null,
        error: null,
        retry_count: 0,
      },
    },
    last_event_sequence: 3,
    updated_at: "2026-04-13T09:05:00.000Z",
  };

  await page.route("**/api/v1/workflows/schema", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        $schema: "https://json-schema.org/draft/2020-12/schema",
        type: "object",
      }),
    });
  });

  await page.route("**/api/v1/workflows?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [workflowDefinition],
        next_cursor: null,
        total: 1,
      }),
    });
  });

  await page.route("**/api/v1/workflows", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }

    workflowDefinition = buildWorkflowDefinition("workflow-new", "KYC Onboarding", 1);
    workflowVersion = buildWorkflowVersion("workflow-new", "KYC Onboarding");

    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(workflowDefinition),
    });
  });

  await page.route("**/api/v1/workflows/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/versions/")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(workflowVersion),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(workflowDefinition),
    });
  });

  await page.route("**/api/v1/executions?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [execution],
        next_cursor: null,
        total: 1,
      }),
    });
  });

  await page.route("**/api/v1/executions", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }

    execution = buildExecution("execution-1", "workflow-new", "running");

    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(execution),
    });
  });

  await page.route("**/api/v1/executions/execution-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(execution),
    });
  });

  await page.route("**/api/v1/executions/execution-1/state", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(executionState),
    });
  });

  await page.route("**/api/v1/executions/execution-1/journal**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        events: [
          {
            id: "execution-1-evt-1",
            execution_id: "execution-1",
            sequence: 1,
            event_type: "EXECUTION_CREATED",
            step_id: null,
            agent_fqn: null,
            payload: {},
            created_at: "2026-04-13T09:00:00.000Z",
          },
          {
            id: "execution-1-evt-2",
            execution_id: "execution-1",
            sequence: 2,
            event_type: "STEP_COMPLETED",
            step_id: "collect_context",
            agent_fqn: "operations/context-loader",
            payload: {},
            created_at: "2026-04-13T09:02:00.000Z",
          },
          {
            id: "execution-1-evt-3",
            execution_id: "execution-1",
            sequence: 3,
            event_type: "REASONING_TRACE_EMITTED",
            step_id: "evaluate_risk",
            agent_fqn: "trust/risk-evaluator",
            payload: {
              reasoning_trace: {
                execution_id: "execution-1",
                step_id: "evaluate_risk",
                tree_id: "tree-1",
                root_branch_id: "branch-1",
                total_branches: 1,
                budget_summary: {
                  mode: "tree_of_thought",
                  max_tokens: 4000,
                  used_tokens: 820,
                  max_rounds: 4,
                  used_rounds: 2,
                  max_cost_usd: 0.35,
                  used_cost_usd: 0.06,
                  status: "completed",
                },
                branches: [
                  {
                    id: "branch-1",
                    parent_id: null,
                    depth: 0,
                    status: "completed",
                    chain_of_thought: [
                      {
                        index: 1,
                        thought: "Aggregate customer signals before policy review.",
                        confidence: 0.71,
                        token_cost: 120,
                      },
                    ],
                    token_usage: {
                      input_tokens: 320,
                      output_tokens: 90,
                      total_tokens: 410,
                      estimated_cost_usd: 0.018,
                    },
                    budget_remaining_at_completion: 3180,
                    created_at: "2026-04-13T09:02:00.000Z",
                    completed_at: "2026-04-13T09:03:00.000Z",
                  },
                ],
              },
            },
            created_at: "2026-04-13T09:03:00.000Z",
          },
        ],
        total: 3,
      }),
    });
  });

  await page.route("**/api/v1/executions/execution-1/steps/*", async (route) => {
    const stepId = route.request().url().split("/steps/")[1] ?? "evaluate_risk";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        step_id: stepId,
        execution_id: "execution-1",
        status: stepId === "evaluate_risk" ? "completed" : "pending",
        inputs: { customer_id: "cust-123", region: "EU" },
        outputs: stepId === "evaluate_risk" ? { summary: "Risk evaluated", score: 0.92 } : null,
        started_at: "2026-04-13T09:02:00.000Z",
        completed_at: stepId === "evaluate_risk" ? "2026-04-13T09:04:00.000Z" : null,
        duration_ms: stepId === "evaluate_risk" ? 120000 : null,
        context_quality_score: stepId === "evaluate_risk" ? 0.88 : null,
        error: null,
        token_usage: stepId === "evaluate_risk"
          ? {
              input_tokens: 420,
              output_tokens: 128,
              total_tokens: 548,
              estimated_cost_usd: 0.0234,
            }
          : null,
      }),
    });
  });

  await page.route("**/api/v1/executions/execution-1/task-plan/evaluate_risk", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        execution_id: "execution-1",
        step_id: "evaluate_risk",
        selected_agent_fqn: "trust/risk-evaluator",
        selected_tool_fqn: null,
        rationale_summary: "Selected the certified evaluator because it matched policy and latency constraints best.",
        considered_agents: [
          {
            fqn: "trust/risk-evaluator",
            display_name: "Risk Evaluator",
            suitability_score: 0.96,
            is_selected: true,
            tags: ["compliance"],
          },
        ],
        considered_tools: [],
        parameters: [
          {
            parameter_name: "customer_id",
            value: "cust-123",
            source: "execution_context",
            source_description: "From execution correlation context",
          },
        ],
        rejected_alternatives: [],
        storage_key: "execution-1/evaluate_risk/task-plan.json",
        persisted_at: "2026-04-13T09:04:00.000Z",
      }),
    });
  });

  await page.route("**/api/v1/analytics/usage?execution_id=execution-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            step_id: "collect_context",
            step_name: "Collect Context",
            agent_fqn: "operations/context-loader",
            model_id: "gpt-5-mini",
            input_tokens: 120,
            output_tokens: 40,
            total_tokens: 160,
            cost_usd: 0.008,
          },
          {
            step_id: "evaluate_risk",
            step_name: "Evaluate Risk",
            agent_fqn: "trust/risk-evaluator",
            model_id: "gpt-5.4",
            input_tokens: 420,
            output_tokens: 128,
            total_tokens: 548,
            cost_usd: 0.0234,
          },
        ],
      }),
    });
  });

  await page.route("**/api/v1/executions/execution-1/pause", async (route) => {
    execution = { ...execution, status: "paused" };
    executionState = { ...executionState, status: "paused" };
    await route.fulfill({ status: 204, body: "" });
  });

  await page.route("**/api/v1/executions/execution-1/resume", async (route) => {
    execution = { ...execution, status: "running" };
    executionState = { ...executionState, status: "running" };
    await route.fulfill({ status: 204, body: "" });
  });
}

test.beforeEach(async ({ page }) => {
  await installAuthState(page);
  await installWorkspaceState(page);
  await installMockWebSocket(page);
  await mockWorkflowEditorMonitorApi(page);
});

test("workflow editor monitor golden path", async ({ page }) => {
  await page.goto("/workflow-editor-monitor");

  await expect(
    page.getByRole("heading", { name: "KYC Onboarding" }),
  ).toBeVisible({ timeout: 15_000 });
  await page.getByRole("link", { name: /New Workflow/i }).click();

  const editor = page.locator(".monaco-editor").first();
  await expect(editor).toBeVisible({ timeout: 15_000 });
  await setMonacoEditorValue(page, workflowYaml);

  await expect(page.getByText("Collect Context")).toBeVisible({ timeout: 15_000 });
  await expect(
    page.getByText("Approval Gate", { exact: true }).first(),
  ).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: /Create Workflow/i }).click();
  await expect(page).toHaveURL(/\/workflow-editor-monitor\/(?:workflow-new|new)$/);

  await page.goto("/workflow-editor-monitor/workflow-new/executions");
  await page.getByRole("button", { name: /Start New Execution/i }).click();
  await page.getByRole("link", { name: /View Monitor/i }).click();

  await expect(
    page.getByRole("heading", { name: "KYC Onboarding monitor" }),
  ).toBeVisible({ timeout: 15_000 });

  await page.evaluate(() => {
    window.__emitWsEvent?.({
      channel: "execution:execution-1",
      type: "step.state_changed",
      payload: {
        step_id: "evaluate_risk",
        new_status: "completed",
      },
    });
    window.__emitWsEvent?.({
      channel: "execution:execution-1",
      type: "budget.threshold",
      payload: {
        tokens: 548,
        cost_usd: 0.0234,
      },
    });
  });

  await page.getByRole("img", { name: /Evaluate Risk/i }).click({ force: true });
  await page.evaluate(() => {
    const tabButton = Array.from(
      document.querySelectorAll("aside button"),
    ).find((button) => button.textContent?.trim() === "Reasoning Trace");

    if (tabButton instanceof HTMLButtonElement) {
      tabButton.click();
    }
  });
  await expect(page.getByRole("heading", { name: "Reasoning tree" })).toBeVisible({
    timeout: 15_000,
  });

  await page.getByRole("button", { name: "Pause" }).click({ force: true });
  await page.getByRole("button", { name: /Pause execution/i }).click();
  await expect(page.getByText("Paused", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: "Resume" }).click({ force: true });
  await page.getByRole("button", { name: /Resume execution/i }).click();
  await expect(page.getByText("Running", { exact: true }).first()).toBeVisible();
});

test("dark mode renders workflow editor monitor without light surfaces", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("theme", "dark");
  });
  await page.emulateMedia({ colorScheme: "dark" });

  await page.goto("/workflow-editor-monitor/new");

  await expect(page.locator(".monaco-editor")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("No workflow graph yet")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page).toHaveScreenshot("workflow-editor-monitor-dark.png", {
    animations: "disabled",
    fullPage: true,
  });
});
