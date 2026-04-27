# Governance

Governance owns policy authoring, compilation, attachment, and runtime enforcement bundles.

Primary entities include policies, policy versions, policy attachments, blocked action records, and compiled bundles. The REST surface manages policies and attachments. Events are emitted for policy lifecycle and blocked tool or memory actions.

Governance is called on hot paths by workflow execution, memory writes, tool gateway operations, and trust workflows.
