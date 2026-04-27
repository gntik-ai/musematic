# Sandbox

Sandbox owns isolated code execution and artifact capture through the Sandbox Manager satellite.

Primary entities include sandbox templates, execution metadata, artifact references, and pod state. The service exposes gRPC methods for execution, file transfer, and lifecycle operations. Events and artifacts are tied back to execution records.

Sandbox pods run with restricted privileges, dropped capabilities, read-only roots where possible, and deny-all network defaults.
