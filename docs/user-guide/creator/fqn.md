# Choosing an FQN

An FQN is the stable external name for an agent. Use a short namespace plus a descriptive agent name, such as `finance.invoice-reviewer`.

Avoid names that encode implementation details, model providers, temporary projects, or individual owners. The agent can change revisions, package formats, and maintainers without changing the FQN.

FQN conventions come from feature 015 and are enforced by the registry. Renames should be rare because workflows, visibility grants, policy bindings, and audit evidence reference the FQN.
