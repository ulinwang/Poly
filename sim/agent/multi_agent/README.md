# Multi-Agent protocol

Poly separates three concerns that were previously implicit in the runner and
Forum implementation:

1. **Decision scheduling** controls the order in which Agent Loops are called.
2. **Interaction protocol** describes what agents publish and what other
   agents actually receive.
3. **Channel state** remains owned by the existing deterministic `Forum`.

## Scheduling

`AgentScheduler.schedule()` receives the current tick and all observed agent
IDs, then returns a validated `TickSchedule`. The default
`SequentialAgentScheduler` preserves observer insertion order, so provider-call
order is unchanged.

Scheduling does not control CLOB matching order. `PolyEnv.step()` keeps its
existing seeded shuffle, which means swapping a decision scheduler does not
silently change market mechanics. The runner emits `agent_schedule` before the
first decision in every tick with both policies made explicit.

Custom schedulers must include every observed agent exactly once. Duplicate,
missing, unknown, or wrong-tick results stop the tick before any provider call
and emit a runner `error` event.

## Interaction messages

Each `InteractionMessage` has stable run/tick/sequence identity plus:

- channel and interaction kind (`post`, `comment`, `follow`, or `read`);
- sender, explicit recipients, and public/direct visibility;
- topic, correlation ID, and source reference;
- channel-specific metadata such as Forum post/comment IDs;
- delivery tick and priority (for example, followed-author reads).

Message IDs use `{run_id}:interaction:{sequence}`. The append-only
`InteractionTranscript` is stored on `Simulation`, so its sequence continues
across checkpoint/resume.

## Forum adapter and replay

`ForumInteractionAdapter` listens to the existing Forum callbacks. Legacy
`forum_post`, `forum_comment`, and `forum_follow` events remain unchanged; the
runner additionally emits one `multi_agent_interaction` event per typed record.
Reads become direct delivery records for every post actually shown to an
agent. This distinguishes public availability from real exposure.

`replay_forum(records)` rebuilds posts, comments, and follow edges solely from
the transcript. Read records do not mutate Forum state, but remain available
for diffusion and collaboration evaluation.

## Budgets

`InteractionBudget` makes per-agent/per-tick Forum read and social-action limits
explicit. The Agent Loop removes exhausted tools before the next generation;
zero-budget tools are never offered even on the first trade call. Web-search
round trips retain their separate bounded budget.

The default remains two Forum reads and two social actions per agent per tick,
matching the behavior before this protocol was introduced.
