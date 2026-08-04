# Versioned prompt management

All production Agent Loop prompts resolve through `PromptResolver`. The local
registry currently pins version `v1` for four prompt families and two
languages:

| Registry key | Langfuse name |
| --- | --- |
| `clob_system` | `poly/clob-system/{en,zh}` |
| `user_state` | `poly/user-state/{en,zh}` |
| `belief_stage` | `poly/belief-stage/{en,zh}` |
| `trade_stage` | `poly/trade-stage/{en,zh}` |

The system and state templates remain under `agent/personas/templates/` for
backward-compatible rendering. Versioned belief/trade templates live under
`agent/prompt/templates/v1/`. Their registry identity, not their directory,
is the stable public contract.

## Resolution order

1. Prompt Management disabled: render local `v1`; no Langfuse import/network.
2. Enabled and remote available: fetch the configured label using the
   Langfuse SDK cache TTL, compile with the same render variables, and retain
   the managed prompt object for generation tracing.
3. SDK fallback object or any fetch/compile exception: return the already
   rendered local prompt and emit `prompt_resolution_warning` through the
   Agent Loop observer.
4. Missing SDK or credentials while enabled: use local fallback and emit the
   same warning; a tick never fails for this reason.

The SDK receives the local render through its `fallback` argument. Poly also
wraps lookup and compile in its own exception boundary because fallback must
remain reliable for Cloud, self-hosted, timeout, and malformed remote-template
failures.

## Identity and reproduction

`ResolvedPrompt.identity` is deeply immutable and records:

- `source`: `local`, `langfuse`, or `fallback`;
- stable prompt name and local/remote version;
- selected label and language;
- SHA-256 hash of the exact rendered content;
- a deep-frozen copy of all template variables.

The full identity is stored on the `Decision` and generation lifecycle event.
Runner/SSE introspection intentionally removes variable values and exposes only
their names plus identity/hash fields. API keys are client construction data,
never template variables or prompt metadata.

## Safe rollout

Create all eight Langfuse text prompts, validate them with a non-production
label, then set `POLYMETL_LANGFUSE_PROMPT_LABEL` to that label in a staging
environment. Promote the label only after semantic/evaluation tests pass.
Changing the label does not require code deployment; cache propagation follows
`POLYMETL_LANGFUSE_PROMPT_CACHE_TTL_SECONDS` (default 300 seconds, 0 disables
caching).
