# Execution

Execution owns runtime state for workflow runs: events, checkpoints, approvals, dispatch leases, task plan records, and compensation records.

Primary entities include executions, execution events, checkpoints, approval waits, dispatch leases, and compensation records. The REST surface exposes execution status, event history, approvals, and control actions. Events are emitted on `execution.events` and `workflow.runtime`.

Execution coordinates with Runtime Controller, Reasoning Engine, Sandbox Manager, Interactions, and Governance.
