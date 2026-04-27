# Evaluation Authoring

Evaluation scenarios test behavior, safety, correctness, and regressions. A good scenario has an objective, input, expected properties, scoring rubric, allowed variance, and remediation owner.

Authoring checklist:

- Keep fixtures deterministic.
- Include negative and adversarial cases.
- Tag scenarios by agent FQN, workspace, and risk area.
- Store large evidence artifacts in object storage.
- Promote only scenarios that are stable enough for CI or release gates.

ATE failures should point to a specific scenario and remediation path.
