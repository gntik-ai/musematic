# Security, Trust, and Privacy Architecture

Security boundaries are enforced across identity, workspace visibility, policy bundles, runtime isolation, secrets, audit evidence, and privacy controls.

Identity starts with the Auth and Accounts contexts. Workspace membership and zero-trust visibility decide what users can see. Policy governance decides what agents and tools can do. Runtime and sandbox services isolate execution. Secret references are resolved through providers instead of being embedded in manifests or logs.

Trust and certification workflows attach evidence before agents reach broad audiences. Privacy compliance records data-subject requests, consent, residency, DLP events, and signed deletion tombstones. Security compliance maps audit-chain events and scanner results to control frameworks.

Operationally, use GID and correlation ID to connect user-visible behavior to logs, traces, audit events, and evidence bundles.
