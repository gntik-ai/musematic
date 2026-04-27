# Runtime

Runtime owns Kubernetes pod lifecycle for agent tasks through the Go Runtime Controller satellite.

Primary entities include warm pool targets, runtime leases, pod state, and task plan metadata. The service exposes gRPC methods to the control plane and emits lifecycle events to Kafka. REST access is mediated through control-plane execution APIs.

Runtime isolates task execution from control-plane request handling and gives operators a clear scaling boundary.
