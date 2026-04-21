# Journey Structure Meta-Test Contract

**Feature**: 072-user-journey-e2e-tests
**Date**: 2026-04-21
**Module**: `tests/e2e/journeys/test_journey_structure.py`

This meta-test enforces FR-003 (each journey crosses ≥ 4 bounded contexts) and FR-004 (each journey includes ≥ 15 assertion points) mechanically via AST inspection. It runs on every `make e2e-journeys` invocation and in CI, failing the build if any journey file falls below the thresholds.

---

## Inputs

The meta-test discovers all files matching `tests/e2e/journeys/test_j[0-9][0-9]_*.py` and parses each one via Python's `ast` module.

## Thresholds

| Rule | Threshold | Source |
|---|---|---|
| Minimum bounded contexts exercised per journey | 4 | FR-003 |
| Minimum assertion points per journey | 15 | FR-004 |
| Minimum journey step narrative decorators per journey | 10 | (D-003 readability guideline — subset of FR-004) |

## Cross-context inventory parsing

Each journey file MUST contain a comment block of the form:

```python
# Cross-context inventory:
# - auth
# - workspaces
# - registry
# - policies
# - trust
# - governance
```

The meta-test:
1. Reads the file as text (not via `ast.parse`) to capture comments.
2. Finds the line matching exactly `# Cross-context inventory:` (case-sensitive, no leading whitespace other than one optional space).
3. Collects subsequent lines matching `# - <context>` until the first blank line, non-comment line, or non-matching comment.
4. Strips each context name and validates against the registry below.
5. Fails if fewer than 4 unique valid contexts are found.

**Valid bounded context registry** (from platform constitution + feature 071's `tests/e2e/suites/` directories):

```
auth, accounts, workspaces, registry, trust, governance, interactions, workflows,
execution, fleets, reasoning, evaluation, agentops, discovery, a2a, mcp, runtime,
storage, ibor, marketplace, policies, context-engineering, memory, knowledge,
websocket, notifications, analytics, connectors, audit
```

An unknown context name fails the meta-test with a clear message ("unknown context 'foo' in journey j03 — must be one of: [registry]").

## Assertion point counting

For each journey file, the meta-test counts the **union** of:

1. **`@journey_step(...)` decorator invocations** — found by walking the AST for `With` nodes whose `context_expr` is a `Call` to a `Name` or `Attribute` resolving to `journey_step`.
2. **Bare `assert` statements** — `ast.Assert` nodes inside async function bodies whose decorators include `@pytest.mark.journey` OR whose module has `JOURNEY_ID` constant.
3. **Fixture-level state verifications** — calls to helpers named `wait_for_execution`, `assert_event_order`, `assert_checkpoint_resumed`, or any function starting with `assert_` from `tests.e2e.journeys.helpers.*`.

**De-duplication**: if an `assert` appears inside a `journey_step` context manager, it counts once (not twice). Practically: the AST walker tags each `journey_step` block as a single "containing" point, then adds any `assert` statements OUTSIDE those blocks.

**Threshold**: ≥ 15 assertion points per journey. Below threshold → build fails with the file name and the counted points.

## Journey-step decorator threshold

Separately, the meta-test counts just the `@journey_step` decorator invocations and requires ≥ 10 per journey. This enforces readability (D-003) — even if a journey has 30 `assert` statements, it must also have 10 narrative decorators so the HTML report tells a coherent story.

## Naming convention enforcement

The meta-test also verifies:

| Required element | Pattern | Failure message |
|---|---|---|
| Module name | `test_j\d{2}_[a-z_]+\.py` | "journey file name must match pattern test_jNN_persona_hint.py" |
| `JOURNEY_ID` constant | `^j\d{2}$` | "JOURNEY_ID must be 'j01'..'j09'" |
| `TIMEOUT_SECONDS` constant | int in [60, 900] | "TIMEOUT_SECONDS must be 60–900" |
| Required markers | `@pytest.mark.journey` AND `@pytest.mark.j{NN}_{persona}` AND `@pytest.mark.timeout(TIMEOUT_SECONDS)` | "missing marker(s): ..." |

## Isolation-scope enforcement

Additionally, the meta-test scans for helper calls (`register_full_agent`, `create_workspace`, etc.) and verifies each one passes `journey_id=JOURNEY_ID` or `JOURNEY_ID` as the first positional arg. Calls that omit the journey ID fail the meta-test with:

> "journey j02 (test_j02_creator_to_publication.py:42): call to `register_full_agent` missing journey_id — resource would not carry the isolation prefix 'j02-test-'"

This prevents accidental cross-journey state pollution at write time.

## Output

On pass: `test_journey_structure` prints a summary table of counts per journey:

```
Journey | Steps | Asserts | Total | Contexts
--------+-------+---------+-------+----------
j01     |   18  |   22    |  40   | 6
j02     |   25  |   30    |  55   | 7
j03     |   22  |   28    |  50   | 8
...
```

On fail: prints the offending journey, the failing check, and the actual-vs-expected values, then raises `AssertionError`. pytest marks the test as failed and CI blocks merge.

## Extensibility

When new journeys are added (e.g. J10 for a new persona), the meta-test automatically discovers them via the `test_j\d{2}_*.py` glob — no changes to the meta-test required.

When new bounded contexts are added to the platform (e.g., a new bounded context `recommendations`), the valid-context registry in the meta-test module must be updated. This is a deliberate gate: adding a context to the registry requires reviewer awareness that journey tests may now legitimately cite it.

---

## Example failure output

```
tests/e2e/journeys/test_journey_structure.py::test_all_journeys_meet_structure FAILED

E   AssertionError: journey structure violations:
E   
E     j03 (test_j03_consumer_discovery_execution.py):
E       - assertion points: 13 (required ≥ 15)
E       - journey_step decorators: 8 (required ≥ 10)
E   
E     j08 (test_j08_external_a2a_mcp.py):
E       - cross-context inventory: 3 contexts (required ≥ 4)
E         Listed: [a2a, mcp, auth]
E         Missing any of: [registry, policies, ...]
E   
E     j07 (test_j07_evaluator_improvement_loop.py):
E       - line 127: call to `register_full_agent` missing journey_id parameter
```

This gives the author an immediate, actionable fix path.
