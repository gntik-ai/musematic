# Simulation

Simulation owns what-if runs, digital twins, simulation artifacts, and isolated execution in the `platform-simulation` namespace.

Primary entities include simulation runs, scenarios, artifacts, and controller state. The service exposes gRPC methods and emits `simulation.events`. REST access is mediated by the control plane.

Simulation is used by evaluation, discovery, fleet testing, and operator experiments.
