# Feature Specification: Scientific Discovery Orchestration

**Feature Branch**: `039-scientific-discovery-orchestration`  
**Created**: 2026-04-15  
**Status**: Draft  
**Input**: User description for hypothesis generation workflows, multi-agent critique, Elo-based tournament ranking, experiment design, generate-debate-evolve cycles, evidence provenance chains, and hypothesis proximity clustering.  
**Requirements Traceability**: FR-346-351, TR-340-343

## User Scenarios & Testing

### User Story 1 - Generate and Rank Hypotheses via Tournament (Priority: P1)

A research operator initiates a discovery session by providing a research question and a dataset or literature corpus. The system orchestrates multiple generation agents to produce hypotheses addressing the question. Each hypothesis is then entered into a pairwise tournament where hypotheses are compared head-to-head by evaluator agents. An Elo-based ranking system tracks scores across rounds, producing a leaderboard ordered by scientific merit.

**Why this priority**: Without hypothesis generation and ranking, no other discovery capability can function. This is the foundational loop — produce ideas, compare them, surface the best.

**Independent Test**: Provide a research question ("What mechanisms drive antibiotic resistance in hospital environments?"). Confirm at least 5 hypotheses are generated. Confirm pairwise comparisons occur. Confirm an Elo-based leaderboard is produced with hypotheses ranked by score.

**Acceptance Scenarios**:

1. **Given** a research question and corpus, **When** the operator starts a discovery session, **Then** the system orchestrates generation agents to produce at least 3 hypotheses, each with a title, description, supporting reasoning, and confidence level.
2. **Given** 5 generated hypotheses, **When** a tournament round executes, **Then** all pairwise combinations are evaluated by a comparison agent, and Elo scores update according to outcomes (win, loss, draw).
3. **Given** a completed tournament round, **When** the operator views the leaderboard, **Then** hypotheses are ordered by Elo score descending with score, rank change since last round, win/loss/draw counts, and timestamp of last update.

---

### User Story 2 - Multi-Agent Critique of Hypotheses (Priority: P1)

After hypotheses are generated, multiple independent reviewer agents evaluate each hypothesis along structured dimensions: internal consistency, novelty relative to existing knowledge, testability (can an experiment verify or falsify it), evidence support strength, and potential impact. Each critique is attributed to its reviewer agent and includes a structured score plus free-text reasoning.

**Why this priority**: Critique is inseparable from generation — without structured evaluation, hypothesis quality cannot be assessed and tournament rankings become arbitrary. This runs alongside US1 as a co-equal P1.

**Independent Test**: Generate 3 hypotheses. Submit them for critique. Confirm each receives evaluations along all 5 dimensions from at least 2 reviewer agents. Confirm each evaluation includes a structured score and reasoning text.

**Acceptance Scenarios**:

1. **Given** a generated hypothesis, **When** submitted for critique, **Then** at least 2 independent reviewer agents produce structured evaluations scoring consistency, novelty, testability, evidence support, and impact.
2. **Given** a critique evaluation, **When** the operator views it, **Then** each dimension shows a score (numeric), a confidence level, free-text reasoning, and the identity of the reviewing agent.
3. **Given** multiple critiques for one hypothesis, **When** aggregated, **Then** the system produces a composite critique summary with per-dimension averages and areas of inter-reviewer disagreement flagged.

---

### User Story 3 - Generate-Debate-Evolve Cycles (Priority: P2)

The operator launches an iterative discovery cycle where: (1) generation agents produce or refine hypotheses, (2) debate agents argue for and against each hypothesis using evidence and reasoning, (3) hypotheses are refined based on debate outcomes, and (4) the refined set is re-ranked via tournament. Cycles repeat until a convergence condition is met (e.g., top-ranked hypothesis score stabilizes across rounds) or a maximum iteration limit is reached. The operator can also manually halt or escalate.

**Why this priority**: This is the full scientific discovery workflow that orchestrates US1 and US2 into a coherent iterative process. It cannot exist without them but delivers the primary value proposition of automated scientific reasoning.

**Independent Test**: Start a generate-debate-evolve session with 3 iterations max. Confirm generation produces hypotheses in cycle 1. Confirm debate occurs with arguments for and against. Confirm hypotheses are refined in cycle 2 based on debate. Confirm convergence check runs after each cycle. Confirm the session terminates at convergence or iteration limit.

**Acceptance Scenarios**:

1. **Given** a configured discovery session, **When** the operator launches a generate-debate-evolve cycle, **Then** cycle 1 executes: generate → critique → tournament rank → debate → refine.
2. **Given** an active cycle where the top-ranked hypothesis Elo score has not changed by more than 5% across 2 consecutive rounds, **When** the convergence check runs, **Then** the system declares convergence and halts the cycle, notifying the operator.
3. **Given** an active cycle that has not converged, **When** the maximum iteration limit is reached, **Then** the system halts with the current best-ranked hypothesis set, marks the session as "iteration_limit_reached", and notifies the operator.
4. **Given** an active cycle, **When** the operator manually halts, **Then** the cycle stops after the current phase completes, the current state is preserved, and the session is marked "operator_halted".

---

### User Story 4 - Design and Execute Discovery Experiments (Priority: P2)

For top-ranked hypotheses, the operator (or an automated trigger) requests experiment design. An experiment design agent creates a structured experiment plan: objective, methodology, expected outcomes, required data, computational resources, and success criteria. The plan is validated against governance rules before execution. Experiments execute in sandbox-isolated environments. Results are captured and linked back to the hypothesis.

**Why this priority**: Experiments extend the discovery loop from theoretical reasoning to empirical validation. This is a P2 because it builds on the hypothesis generation + ranking foundation but adds significant value by enabling hypothesis testing.

**Independent Test**: Take the top-ranked hypothesis from a tournament. Request experiment design. Confirm a structured plan is produced with all required sections. Confirm governance validation passes. Confirm the experiment executes in a sandboxed environment. Confirm results are linked to the originating hypothesis.

**Acceptance Scenarios**:

1. **Given** a top-ranked hypothesis, **When** experiment design is requested, **Then** an experiment design agent produces a plan with: objective, methodology, expected outcomes, required data, computational resources, and success criteria.
2. **Given** an experiment plan, **When** submitted for execution, **Then** the system validates the plan against workspace governance rules (policy conformance, sandbox constraints, resource limits) and rejects non-compliant plans with specific violations listed.
3. **Given** a governance-approved plan, **When** the experiment executes, **Then** execution occurs in a sandbox environment, results are captured, and a link is created between the experiment results and the originating hypothesis.
4. **Given** completed experiment results, **When** the results support the hypothesis, **Then** the hypothesis evidence strength is updated and the tournament ranking reflects the empirical validation as a positive signal.

---

### User Story 5 - Trace Evidence Provenance Chains (Priority: P3)

A researcher or auditor wants to understand how a discovery conclusion was reached. They select a hypothesis and trace its full provenance: which agents generated it, what evidence supports or contradicts it, which critiques were applied, what debates occurred, what experiments were run, and how it evolved across generate-debate-evolve cycles. The provenance forms a directed graph showing the full reasoning chain from initial generation through refinement to current state.

**Why this priority**: Provenance is essential for scientific reproducibility and trust but does not block the core discovery workflow. It can be built after the generation, critique, and experiment machinery is in place since it reads data produced by those systems.

**Independent Test**: Run a 2-cycle generate-debate-evolve session that includes experiment execution. Select the top hypothesis. Query its provenance. Confirm the chain shows: initial generation event, critique events, debate arguments, refinement events, experiment results, and links to all participating agents.

**Acceptance Scenarios**:

1. **Given** a hypothesis that has been through generation, critique, debate, and refinement, **When** the operator queries its provenance, **Then** the system returns a directed graph of events in chronological order showing each transformation and the agent responsible.
2. **Given** a hypothesis with experiment results, **When** provenance is queried, **Then** experiment evidence nodes appear in the graph linked to the hypothesis with relationship types (supports, contradicts, inconclusive).
3. **Given** a provenance graph, **When** the operator queries for all evidence supporting a hypothesis, **Then** the system returns all evidence nodes with their source, confidence, and relationship type.

---

### User Story 6 - Explore Hypothesis Landscape via Proximity Clustering (Priority: P3)

After multiple discovery sessions produce a large set of hypotheses, the operator wants to understand the landscape: which areas are well-explored (many similar hypotheses), which are underrepresented (gaps), and which hypotheses are effectively redundant. The system computes semantic embeddings for all hypotheses, clusters them by similarity, and identifies clusters with high density (over-explored) and regions with low density (gaps). This information feeds back into the generation agent to bias future hypothesis generation toward underrepresented areas.

**Why this priority**: Proximity clustering is an advanced optimization that improves hypothesis diversity over many cycles. It depends on having a substantial corpus of hypotheses from US1-US3 and adds strategic direction to the generation process.

**Independent Test**: Generate 20+ hypotheses across multiple sessions. Trigger proximity computation. Confirm hypotheses are clustered by semantic similarity. Confirm high-density clusters are flagged. Confirm gap regions are identified. Confirm the next generation cycle produces hypotheses biased toward gap areas.

**Acceptance Scenarios**:

1. **Given** 20+ hypotheses, **When** proximity computation runs, **Then** hypotheses are grouped into semantic clusters with similarity scores, and each cluster has a centroid description summarizing its theme.
2. **Given** proximity clusters, **When** the operator views the landscape summary, **Then** high-density clusters (>5 hypotheses with >0.85 similarity) are flagged as "over-explored" and regions with no hypotheses within 0.5 similarity of any existing cluster centroid are flagged as "gap".
3. **Given** identified gaps and over-explored areas, **When** a new generation cycle starts, **Then** the generation agent receives landscape context that biases it toward gap areas, and the resulting hypotheses are measurably more diverse (average inter-hypothesis similarity decreases).

---

### User Story 7 - Visualize Hypothesis Proximity Network (Priority: P4)

The operator views the hypothesis landscape as an interactive network graph where nodes represent hypotheses, edges represent semantic similarity above a threshold, and clusters are color-coded. The operator can zoom, pan, select nodes to see details, filter by cluster, and observe how the landscape evolves across generate-debate-evolve cycles.

**Why this priority**: Visualization is a presentation layer that depends on all backend computation being in place (US6). It provides significant UX value but is not required for the proximity-biased generation to work.

**Independent Test**: Compute proximity clusters (US6). Open the visualization page. Confirm nodes appear with cluster colors. Confirm edges connect similar hypotheses. Confirm clicking a node shows hypothesis details. Confirm filtering by cluster hides non-matching nodes.

**Acceptance Scenarios**:

1. **Given** computed proximity clusters, **When** the operator opens the hypothesis landscape view, **Then** a network graph renders with nodes positioned by similarity, edges connecting hypotheses above a configurable similarity threshold, and clusters distinguished by color.
2. **Given** the network graph, **When** the operator clicks a hypothesis node, **Then** a detail panel shows the hypothesis title, description, Elo score, cluster assignment, and links to critiques and experiments.
3. **Given** multiple generate-debate-evolve cycles, **When** the operator selects different cycle snapshots, **Then** the graph updates to reflect the hypothesis landscape at that point in time, allowing comparison of landscape evolution.

---

### Edge Cases

- What happens when generation agents produce duplicate or near-identical hypotheses? The system detects duplicates via semantic similarity (>0.95) and merges them, preserving provenance for both originals.
- What happens when a tournament has an odd number of hypotheses? The system uses a bye mechanism — one hypothesis receives a bye per round, with no Elo change.
- How does the system handle a debate that produces no clear outcome? The debate is recorded as a "draw" in the tournament, with minimal Elo adjustment for both sides.
- What happens when an experiment fails (runtime error, timeout)? The experiment result is recorded as "failed" with the error, linked to the hypothesis as inconclusive evidence, and does not affect Elo score.
- What if all generation agents produce low-confidence hypotheses? The system flags the session as "low_yield" and suggests the operator refine the research question or provide additional context.
- What happens when proximity clustering finds no gaps? The system reports a "saturated" landscape and suggests broadening the research scope or increasing the novelty threshold for generation.
- What if the convergence condition is never met within the iteration limit? The session completes at the limit with "iteration_limit_reached" status and presents the best-ranked hypotheses as preliminary findings.

## Requirements

### Functional Requirements

- **FR-001**: System MUST orchestrate multiple generation agents to produce structured hypotheses (title, description, reasoning, confidence) from a research question and optional corpus
- **FR-002**: System MUST support pairwise tournament comparisons where hypotheses are evaluated head-to-head by comparison agents
- **FR-003**: System MUST maintain an Elo-based ranking that updates after each pairwise comparison, using standard Elo formulas with a configurable K-factor
- **FR-004**: System MUST produce a leaderboard ordered by Elo score with rank change, win/loss/draw counts, and last update timestamp
- **FR-005**: System MUST orchestrate at least 2 independent reviewer agents per hypothesis for structured critique
- **FR-006**: Each critique MUST evaluate 5 dimensions: consistency, novelty, testability, evidence support, and impact — each with a numeric score, confidence level, and free-text reasoning
- **FR-007**: System MUST aggregate multiple critiques into a composite summary with per-dimension averages and inter-reviewer disagreement flags
- **FR-008**: System MUST support iterative generate-debate-evolve cycles: generate → critique → rank → debate → refine, repeating until convergence or iteration limit
- **FR-009**: Convergence MUST be checked after each cycle: if the top-ranked hypothesis Elo score changes by less than a configurable threshold across N consecutive rounds, the cycle halts
- **FR-010**: The operator MUST be able to manually halt a generate-debate-evolve cycle; the system preserves current state and marks the session accordingly
- **FR-011**: System MUST support experiment design: a design agent produces a structured plan (objective, methodology, expected outcomes, required data, resources, success criteria)
- **FR-012**: Experiment plans MUST be validated against workspace governance rules before execution
- **FR-013**: Experiments MUST execute in sandbox-isolated environments with results captured and linked to the originating hypothesis
- **FR-014**: Positive experiment results MUST feed back into Elo rankings as a validation signal
- **FR-015**: System MUST maintain a provenance graph linking each hypothesis to: generating agent, critiques, debate arguments, refinements, experiments, and evidence
- **FR-016**: Provenance MUST be queryable: given a hypothesis, return the full chain of events and agents that contributed to its current state
- **FR-017**: Evidence nodes in provenance MUST have typed relationships to hypotheses: supports, contradicts, or inconclusive
- **FR-018**: System MUST compute semantic embeddings for all hypotheses and cluster them by similarity
- **FR-019**: Clustering MUST identify over-explored areas (high-density clusters) and underrepresented gaps (low-density regions)
- **FR-020**: Gap identification MUST feed into the generation agent as landscape context to bias future generation toward diversity
- **FR-021**: System MUST detect near-duplicate hypotheses (>0.95 similarity) and merge them with provenance preserved
- **FR-022**: Tournament MUST handle odd hypothesis counts using a bye mechanism
- **FR-023**: Failed experiments MUST be recorded as inconclusive evidence without affecting Elo rankings
- **FR-024**: System MUST flag low-yield sessions and suggest research question refinement
- **FR-025**: Hypothesis landscape MUST be viewable as an interactive network graph with cluster coloring, similarity edges, and node detail panels
- **FR-026**: Network graph MUST support cycle-by-cycle snapshot comparison to show landscape evolution

### Key Entities

- **Hypothesis**: A structured scientific conjecture with title, description, reasoning, confidence, Elo score, and current rank. Linked to generating agent, critiques, debates, and experiments.
- **HypothesisCritique**: A structured evaluation of a hypothesis along 5 dimensions by a specific reviewer agent. Includes per-dimension scores, confidence levels, and reasoning.
- **TournamentRound**: A set of pairwise comparisons within a single ranking iteration. Tracks which pairs were compared, outcomes, and resulting Elo changes.
- **EloScore**: The current and historical Elo rating for a hypothesis within a discovery session. Tracks score history, win/loss/draw counts.
- **DiscoveryExperiment**: A structured experiment plan linked to a hypothesis, with governance validation status, sandbox execution status, and results.
- **DiscoveryEvidence**: A piece of evidence (from experiment, literature, or reasoning) linked to a hypothesis via a typed relationship (supports/contradicts/inconclusive).
- **GenerateDebateEvolveCycle**: A single iteration of the discovery loop, tracking generation outputs, debate records, refinements, and convergence metrics.
- **DiscoverySession**: The top-level container for a discovery workflow, holding the research question, configuration, cycle history, and current state (active/converged/halted/iteration_limit).
- **HypothesisCluster**: A group of semantically similar hypotheses with a centroid description, density metric, and gap/over-explored classification.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A discovery session produces at least 5 ranked hypotheses from a research question within 10 minutes of session start
- **SC-002**: Each hypothesis receives structured critiques from at least 2 reviewers within 3 minutes of generation
- **SC-003**: Elo rankings converge (top hypothesis score stable within 5% across 2 rounds) for 80% of sessions within 5 cycles
- **SC-004**: Experiment designs are generated and governance-validated within 2 minutes per hypothesis
- **SC-005**: Provenance queries return the full chain for any hypothesis in under 5 seconds
- **SC-006**: Proximity clustering identifies at least 1 gap and 1 over-explored area for sessions with 20+ hypotheses
- **SC-007**: Generation diversity improves measurably — average inter-hypothesis similarity decreases by at least 10% after proximity-biased generation
- **SC-008**: Test coverage reaches 95% or higher for all discovery modules

## Assumptions

- Generation, critique, debate, and experiment design agents are existing platform agents configured with appropriate roles and tools — the discovery system orchestrates them, it does not implement the agents themselves
- Hypotheses are text-based structured documents; image, diagram, or formula-heavy hypotheses are out of scope for v1
- The Elo rating system uses standard chess K-factor (K=32) as default, configurable per session
- "Experiments" are computational (code executed in sandbox) — not physical laboratory experiments
- Convergence threshold defaults: Elo change < 5% across 2 consecutive rounds; configurable per session
- Maximum iteration limit defaults to 10 cycles; configurable per session
- Proximity clustering is a background computation, not real-time — it runs after each generate-debate-evolve cycle completes
- The frontend network visualization (US7) is a separate frontend feature that can be deferred without impacting backend discovery capabilities
- Discovery sessions are workspace-scoped; hypotheses from different workspaces are not compared
