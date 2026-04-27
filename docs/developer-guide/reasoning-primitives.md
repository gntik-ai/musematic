# Reasoning Primitives

Reasoning primitives describe how the reasoning engine budgets, branches, converges, and records traces.

Core concepts:

| Primitive | Meaning |
| --- | --- |
| Mode | Strategy selected for a task, such as direct, chain, tree, or adaptive reasoning. |
| Branch | Candidate path evaluated under a budget. |
| Budget | Token, time, or branch limit enforced before provider dispatch. |
| Convergence | Signal that independent branches agree closely enough to stop. |
| Trace | Persisted explanation of branch decisions and outcomes. |
| Self-correction | Runtime ability to revise output after detecting mismatch or policy risk. |

Keep traces useful for review without exposing sensitive prompt material unnecessarily.
