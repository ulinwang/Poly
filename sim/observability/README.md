# Poly observability

Poly keeps the Agent Loop lifecycle backend-neutral. This package is an
optional adapter from runner and Agent Loop events to Langfuse Python SDK v4.
It is disabled by default and the normal path does not import Langfuse.

## Trace model

```text
poly.experiment                         one run/session
└── poly.tick.<n>                       deterministic tick boundary
    └── poly.agent-loop                 one agent decision
        ├── poly.generation.<stage>      provider call + tokens/latency
        └── poly.tool.<name>             bounded tool execution
```

The session is tagged `poly` and `agent-simulation`. Observation metadata
includes `run_id`, `tick`, `agent_id`, `decision_id`, stage/iteration,
persona, token budget, environment, release, and market identity where
available. Generation observations carry model, token usage, status, native
observation duration, and the resolved local/fallback/managed prompt identity.
Managed Langfuse prompt objects are linked directly to their generation.
Decision and end-of-run evaluation scores are mirrored onto the matching Agent
Loop and experiment observations.

## Enable

```bash
uv sync --extra observability

export POLYMETL_LANGFUSE_ENABLED=true
export POLYMETL_LANGFUSE_PUBLIC_KEY=pk-lf-...
export POLYMETL_LANGFUSE_SECRET_KEY=sk-lf-...
export POLYMETL_LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

For self-hosting, set `POLYMETL_LANGFUSE_BASE_URL` to the instance's HTTPS
origin. `LANGFUSE_*` variables used directly by the upstream SDK are not
required because Poly passes its `POLYMETL_LANGFUSE_*` settings explicitly.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `POLYMETL_LANGFUSE_ENABLED` | `false` | Master switch; false means zero SDK import/network |
| `POLYMETL_LANGFUSE_BASE_URL` | Langfuse Cloud | Cloud or self-hosted origin |
| `POLYMETL_LANGFUSE_ENVIRONMENT` | `development` | Deployment/environment dimension |
| `POLYMETL_LANGFUSE_RELEASE` | unset | Application version or Git SHA |
| `POLYMETL_LANGFUSE_SAMPLE_RATE` | `1.0` | SDK trace sampling ratio, from `0` to `1` |
| `POLYMETL_LANGFUSE_CAPTURE_POLICY` | `metadata` | `metadata` or `full` |
| `POLYMETL_LANGFUSE_FLUSH_TIMEOUT_SECONDS` | `5` | Maximum wait at terminal run states |

Credentials are required only when enabled. If either credential or the SDK
is absent, Poly logs a warning and uses a no-op observer.

## Data capture and failure behavior

`metadata` exports identifiers, numeric metrics, status, model/tool names,
budgets, prompt identity, evaluation scores, and token usage. It drops prompt
text, prompt variable values, messages,
tool arguments, search results, reasoning, and generated text.

`full` additionally exports visible prompt/message/tool input and model output
with bounded string length. Both policies redact credential-like keys,
authorization/cookies, raw responses, and `reasoning_content`. The decision
runtime already removes hidden provider reasoning before lifecycle delivery.
Private in-process integration objects (keys beginning with `_`) are never
serialized.

All adapter calls are fail-open. Initialization, observation updates, exporter
outages, and flush failures cannot stop or mutate a simulation. Normal
completion, pause, cancellation, and fatal error all close open observations
and trigger a bounded flush; a slow flush continues in a daemon thread after
the configured timeout.
