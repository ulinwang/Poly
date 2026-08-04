# Agent Runtime lifecycle

Poly keeps market simulation deterministic while allowing each agent to run a
bounded LLM/tool loop. The runtime is split into three layers:

1. `runner.runner_stream` owns experiment and tick scheduling. The default
   scheduler remains sequential so event order and replay behavior are stable.
2. `agent.decision.runtime.decide` owns one agent decision. It preserves the
   existing two-stage belief/trade flow and the bounded information/Forum tool
   loop.
3. `agent.loop` defines backend-neutral lifecycle context and observer
   contracts. Tracing and evaluation integrations subscribe here instead of
   being coupled to the decision implementation.

## Stable identity

Each decision receives an immutable `AgentLoopContext`:

```text
run_id
└── tick
    └── agent_id
        └── decision_id = {run_id}:tick:{tick}:agent:{agent_id}
            └── step_id = {decision_id}:{stage}:{iteration}
```

The live runner derives `run_id` from `Simulation.sim_id`, which survives a
checkpoint/resume. Direct callers that do not pass a context receive a
`standalone` context for compatibility.

## Lifecycle

The runtime emits ordered events with a monotonic per-decision sequence:

- loop start;
- prompt build;
- belief generation and parse;
- trade generations and tool calls (including every bounded continuation);
- final parse;
- evaluation extension point;
- finish and loop completion.

Stages and iterations are explicit, so a subscriber can reconstruct the
hierarchy without inferring it from prompt text or provider responses.

## Observer contract

Observers implement one method:

```python
class MyObserver:
    def on_event(self, event):
        ...
```

Pass an observer to `decide(..., observer=...)` or a shared observer to
`run_stream(..., agent_loop_observer=...)`. The default observer is a no-op.
Observer exceptions are swallowed and logged at debug level; tracing,
evaluation, or exporter failures must never change a market action or stop a
simulation. `CompositeAgentLoopObserver` can fan events out to several
independent integrations.

Lifecycle payloads may contain rendered prompts, tool arguments, tool results,
and visible model output for local subscribers. Provider-only hidden reasoning
is deliberately removed before events are emitted. External telemetry adapters
must still apply their configured capture/redaction policy before export. API
keys are never placed in lifecycle events.

## Compatibility guarantees

- The public `decide()` call remains valid without new arguments.
- Existing provider, retry, timeout, token-budget, HOLD fallback, and Forum
  behavior remains unchanged.
- `Decision.decision_id` is additive and defaults to an empty string for
  manually constructed/legacy decisions.
- Langfuse and other telemetry SDKs are not required by the core runtime.

The deterministic multi-agent scheduler and interaction transcript now build
on this contract without changing Agent Loop internals. The next layers are an
optional Langfuse observer, versioned prompt resolution, and local/remote
evaluation adapters.
