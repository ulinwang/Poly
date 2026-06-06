import { useExperimentStore } from '../stores';
import type { AgentSnapshot } from '../types';

/**
 * The slice of the experiment store actions an event dispatch needs. Both the
 * live SSE hook and the replay player apply events through this same surface so
 * the kind→store mapping lives in exactly one place (no two copies to drift).
 */
export type ExperimentStoreApi = ReturnType<typeof useExperimentStore.getState>;

function nowStr(): string {
  return new Date().toTimeString().slice(0, 8);
}

/**
 * Apply a single recorded/streamed event (identified by its NDJSON `kind`,
 * which matches the SSE event name) to the experiment store. This is the single
 * source of truth for how an event mutates UI state; `useSSE` calls it per
 * incoming SSE event and the replay player calls it per recorded event.
 *
 * `kind` values that only signal lifecycle to the live transport (`ping`,
 * `end`, `done`) are intentionally not handled here — the caller owns
 * running/connection state. Replay, which has no live connection, can pass
 * those kinds harmlessly (they are no-ops).
 */
export function applyEvent(
  store: ExperimentStoreApi,
  kind: string,
  data: Record<string, unknown>,
): void {
  // Mirror the raw event into the events log, using the same {event, data}
  // shape the SSE handler used.
  store.addEvent({ event: kind, data });

  switch (kind) {
    case 'run_started':
      store.setPaused(false);
      store.addTickLog({ id: Date.now() + Math.random(), time: nowStr(), label: 'start', msg: `Run started: ${data.slug ?? ''}`, kind: 'info' });
      break;

    case 'market_resolved':
      store.addTickLog({ id: Date.now() + Math.random(), time: nowStr(), label: 'market', msg: (data.question as string) || 'Market resolved', kind: 'info' });
      break;

    case 'priors_ready':
      store.addTickLog({ id: Date.now() + Math.random(), time: nowStr(), label: 'priors', msg: `Priors ready: μ=${typeof data.signal_mu === 'number' ? data.signal_mu.toFixed(3) : '?'}`, kind: 'info' });
      break;

    case 'population_built':
      store.addTickLog({ id: Date.now() + Math.random(), time: nowStr(), label: 'agents', msg: `${data.n_agents} agents built`, kind: 'info' });
      break;

    case 'env_ready':
      store.setMetrics({
        yesMid: (data.yes_mid_post_seed as number) ?? 0.5,
        totalTicks: (data.n_ticks as number) ?? 0,
      });
      store.addTickLog({ id: Date.now() + Math.random(), time: nowStr(), label: 'env', msg: `Env ready: YES=${typeof data.yes_mid_post_seed === 'number' ? data.yes_mid_post_seed.toFixed(3) : '?'}`, kind: 'info' });
      break;

    case 'tick_started':
      store.setMetrics({ currentTick: data.tick as number });
      break;

    case 'agent_decision':
      store.addDecision({
        id: Date.now() + Math.random(),
        agent_id: data.agent_id as number,
        tick: data.tick as number,
        persona_type: data.persona_type as string,
        order_type: data.order_type as string,
        side: data.side as string,
        outcome: data.outcome as string,
        price: data.price as number,
        size_usd: data.size_usd as number,
        reasoning: data.reasoning as string,
        api_latency_ms: data.api_latency_ms as number,
        api_error: data.api_error as string,
      });
      break;

    case 'tick_metrics':
      store.addTickMetrics({
        tick: data.tick as number,
        yes_mid: data.yes_mid as number,
        no_mid: data.no_mid as number,
        parity_gap: data.parity_gap as number,
        n_fills: data.n_fills as number,
        ret: data.ret as number,
      });
      break;

    case 'agent_snapshots': {
      const agents = Array.isArray(data.agents) ? (data.agents as AgentSnapshot[]) : [];
      store.addAgentSnapshots(agents);
      break;
    }

    case 'forum_post':
      store.addForumPost({
        tick: data.tick as number,
        author_id: data.author_id as number,
        post_id: data.post_id as number,
        content: (data.content as string) ?? '',
      });
      break;

    case 'forum_comment':
      store.addForumComment({
        tick: data.tick as number,
        author_id: data.author_id as number,
        post_id: data.post_id as number,
        comment_id: data.comment_id as number,
        content: (data.content as string) ?? '',
      });
      break;

    case 'forum_follow':
      store.addFollow({
        tick: data.tick as number,
        agent_id: data.agent_id as number,
        target_id: data.target_id as number,
      });
      break;

    case 'agent_decision_error':
      store.addTickLog({
        id: Date.now() + Math.random(), time: nowStr(), label: 'dec_err',
        msg: `Agent ${data.agent_id} tick ${data.tick}: ${data.message}`, kind: 'error',
      });
      break;

    case 'tick_finished': {
      const yesMid = (data.yes_mid as number) ?? 0.5;
      store.setMetrics({
        yesMid,
        nFills: (data.n_fills as number) ?? 0,
        nActions: (data.n_actions as number) ?? 0,
        lastTickElapsed: (data.elapsed_s as number) ?? 0,
      });
      const history = [...store.metrics.yesMidHistory, yesMid];
      if (history.length > 500) history.shift();
      store.setMetrics({ yesMidHistory: history });
      store.addTickLog({
        id: Date.now() + Math.random(), time: nowStr(), label: 'tick',
        msg: `Tick ${data.tick}: YES=${yesMid.toFixed(3)} fills=${data.n_fills} actions=${data.n_actions}`, kind: 'info',
      });
      break;
    }

    case 'settled':
      store.setMetrics({
        yesMid: (data.yes_mid_final as number) ?? 0.5,
        nFills: (data.n_fills as number) ?? 0,
        nActions: (data.n_actions as number) ?? 0,
      });
      store.addTickLog({
        id: Date.now() + Math.random(), time: nowStr(), label: 'settled',
        msg: `Settled: YES=${typeof data.yes_mid_final === 'number' ? data.yes_mid_final.toFixed(3) : '?'} fills=${data.n_fills}`, kind: 'info',
      });
      break;

    case 'error':
      if (data.message) store.setError(data.message as string);
      store.addTickLog({ id: Date.now() + Math.random(), time: nowStr(), label: 'error', msg: (data.message as string) || 'error', kind: 'error' });
      break;

    case 'cancelled':
      store.addTickLog({ id: Date.now() + Math.random(), time: nowStr(), label: 'cancel', msg: `Cancelled at tick ${data.tick ?? '?'}`, kind: 'warn' });
      break;

    case 'paused':
      store.addTickLog({ id: Date.now() + Math.random(), time: nowStr(), label: 'pause', msg: `Paused at tick ${data.tick ?? '?'} (checkpointed)`, kind: 'warn' });
      break;

    case 'run_resumed':
      store.setPaused(false);
      store.addTickLog({ id: Date.now() + Math.random(), time: nowStr(), label: 'resume', msg: `Resumed from tick ${data.resume_tick ?? '?'}`, kind: 'info' });
      break;

    case 'done':
      store.addTickLog({ id: Date.now() + Math.random(), time: nowStr(), label: 'done', msg: 'Simulation complete', kind: 'info' });
      break;

    // ping / end: live-transport lifecycle, handled by the caller.
    default:
      break;
  }
}
