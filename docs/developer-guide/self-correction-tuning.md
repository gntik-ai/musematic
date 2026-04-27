# Self-Correction Tuning

Self-correction lets a workflow revise or halt output when quality, safety, or policy checks fail.

Tune in this order:

1. Define the detection signal.
2. Set a correction budget.
3. Limit retry and branch counts.
4. Record before-and-after traces.
5. Evaluate corrected output against the original scenario.

Avoid unbounded correction loops. A failed correction should produce a clear error or human attention request.
