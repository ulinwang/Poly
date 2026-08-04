# Agent Loop evaluation

Poly evaluates Agent Loop behavior with deterministic, provider-free checks.
Local runner events are authoritative; Langfuse receives an optional mirror of
the same numeric scores when tracing is enabled.

Per-decision scores cover parsed schema validity, terminal convergence, action
validity, token/social budget compliance, belief validity/presence, and prompt
reproducibility. End-of-run scores cover transcript sequencing, delivery and
correlation correctness, interaction budgets, scheduler coverage, participant
coverage, and belief calibration (Brier skill, using the resolved outcome when
available or the final simulated midpoint otherwise).

Run the checked-in offline regression dataset without any LLM credentials:

```bash
PYTHONPATH=sim:research:. python -m evaluation.agent_loop.cli \
  tests/fixtures/agent_loop_eval.jsonl --fail-on-hard
```

The JSONL input contains fixed parsed Decisions, runtime budgets and expected
score names. It never invokes an LLM. Add representative failure and edge cases
before changing prompts, parsing, tools or loop budgets.

To copy cases to a Langfuse dataset, install the optional SDK, configure its
standard environment credentials, and explicitly add
`--langfuse-dataset DATASET_NAME`. Add
`--langfuse-experiment EXPERIMENT_NAME` to run the deterministic task over the
synced Langfuse dataset and create a comparable dataset run. Dataset sync and
experiments are never performed during a normal simulation or CI run.

`run_langfuse_experiment(..., evaluators=(...))` accepts Langfuse-compatible
evaluators as an explicit extension point, including an LLM-as-a-judge. Such a
judge must remain optional and must not replace the hard deterministic
regression gate.
