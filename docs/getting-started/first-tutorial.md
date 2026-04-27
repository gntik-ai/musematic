# First Tutorial

This tutorial gives you a 30-minute path through the core lifecycle: register an agent, invoke it through a workflow, observe the execution, and inspect the evidence left behind.

## 1. Start a Local Environment

Follow the [Quick Start](quick-start.md) and wait until the control plane, UI, Redis, Kafka, PostgreSQL, and supporting stores are ready.

## 2. Register an Agent

Open the Agent Catalog or use the Registry API to create a profile with a namespace, name, purpose, supported inputs, and package metadata. Use an FQN that can survive ownership changes, for example `demo.summarizer`.

## 3. Attach Policy and Visibility

Grant visibility to your workspace and attach a basic policy bundle that allows the tutorial purpose. In a production workspace, this is where you would add tool restrictions, model restrictions, budget rules, and output sanitization.

## 4. Create a Workflow

Create a simple workflow with one agent invocation and one verification step. Keep the workflow small so you can see each execution event clearly. If you use YAML, validate it before submitting to avoid `WORKFLOW_YAML_INVALID` or `WORKFLOW_SCHEMA_INVALID`.

## 5. Run and Observe

Start an execution. Watch the realtime updates from the UI or subscribe to the `execution` and `reasoning` WebSocket channels. Confirm that the execution has a GID, step events, runtime lifecycle events, and a final status.

## 6. Inspect Evidence

Open the execution detail, reasoning traces, and audit events. Note how the platform records the actor, workspace, policy decisions, runtime task plan, and artifacts. This is the same evidence chain operators and auditors use later.

## 7. Next Steps

Read [Building Agents](../developer-guide/building-agents.md), [MCP Integration](../developer-guide/mcp-integration.md), and the [REST API](../api-reference/rest-api.md) when you are ready to automate the same flow from code.
