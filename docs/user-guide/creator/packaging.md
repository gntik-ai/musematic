# Packaging

Agent packages should be reproducible, versioned, and small enough for repeatable runtime deployment. Include runtime requirements, entry points, test fixtures, and metadata that the registry can index.

Package revisions are separate from the FQN. A new revision can update implementation while preserving workflows and policy bindings. Use release notes to document changed behavior, new tools, safety changes, and migration notes.

Before requesting certification, run local tests and a workspace-scoped execution.
