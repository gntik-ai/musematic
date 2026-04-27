# Observing Execution

Execution views show status, current step, runtime events, artifacts, and errors. Use them whenever a conversation triggers a workflow or a long-running agent task.

The status timeline is fed by execution and runtime lifecycle events. A running step can be waiting for an approval, retrying after a transient failure, dispatching to a runtime pod, or collecting an artifact. Failed steps should include an error code, correlation ID, and remediation hint.

For deeper debugging, open the reasoning trace, logs, and linked runbook when the UI provides one.
