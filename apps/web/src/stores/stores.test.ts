import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useSettingsStore, useMarketStore, useExperimentStore } from './index';
import { applyEvent } from '../lib/applyEvent';

// Zustand stores are singletons — reset between tests by mutating state directly
describe('Settings store', () => {
  beforeEach(() => {
    useSettingsStore.setState({
      apiSettings: { provider: 'deepseek', model: 'deepseek-chat', api_key: '', api_key_set: false, temperature: 0.7, max_tokens: 2048 },
      darkMode: false,
      sidebarCollapsed: false,
    });
  });

  it('toggles dark mode', () => {
    expect(useSettingsStore.getState().darkMode).toBe(false);
    useSettingsStore.getState().toggleDarkMode();
    expect(useSettingsStore.getState().darkMode).toBe(true);
  });

  it('updates api settings partially', () => {
    useSettingsStore.getState().updateApiSettings({ temperature: 1.0 });
    expect(useSettingsStore.getState().apiSettings.temperature).toBe(1.0);
    expect(useSettingsStore.getState().apiSettings.provider).toBe('deepseek');
  });
});

describe('Market store', () => {
  beforeEach(() => {
    useMarketStore.setState({
      markets: [],
      selectedSlug: null,
      category: 'All',
      searchQuery: '',
      loading: false,
      error: null,
    });
  });

  it('sets and reads search query', () => {
    useMarketStore.getState().setSearchQuery('bitcoin');
    expect(useMarketStore.getState().searchQuery).toBe('bitcoin');
  });

  it('filters markets by category', () => {
    useMarketStore.getState().setCategory('Crypto');
    expect(useMarketStore.getState().category).toBe('Crypto');
  });
});

describe('Experiment store', () => {
  beforeEach(() => {
    useExperimentStore.getState().resetSimulation();
  });

  afterEach(() => {
    useExperimentStore.getState().resetSimulation();
  });

  it('resets simulation state', () => {
    useExperimentStore.getState().setRunning(true);
    useExperimentStore.getState().addDecision({
      id: 1, agent_id: 0, tick: 0, persona_type: 'alpha',
      order_type: 'buy', side: 'yes', outcome: 'YES', price: 0.55,
      size_usd: 100, reasoning: 'test', api_latency_ms: 150,
    });
    useExperimentStore.getState().resetSimulation();
    const s = useExperimentStore.getState();
    expect(s.running).toBe(false);
    expect(s.decisions.length).toBe(0);
    expect(s.metrics.yesMid).toBe(0.5);
  });

  it('adds decisions with FIFO cap', () => {
    const store = useExperimentStore.getState();
    for (let i = 0; i < 410; i++) {
      store.addDecision({
        id: i, agent_id: i % 20, tick: Math.floor(i / 20),
        persona_type: 'alpha', order_type: 'buy', side: 'yes',
        outcome: 'YES', price: 0.5, size_usd: 10,
        reasoning: '', api_latency_ms: 100,
      });
    }
    expect(useExperimentStore.getState().decisions.length).toBe(400);
  });

  it('adds tick log with FIFO cap', () => {
    const store = useExperimentStore.getState();
    for (let i = 0; i < 310; i++) {
      store.addTickLog({
        id: i, time: '12:00:00', label: 'tick', msg: `tick ${i}`, kind: 'info',
      });
    }
    expect(useExperimentStore.getState().tickLog.length).toBe(300);
  });

  it('merges metrics partially', () => {
    const store = useExperimentStore.getState();
    store.setMetrics({ yesMid: 0.75, nFills: 12 });
    const s = useExperimentStore.getState();
    expect(s.metrics.yesMid).toBe(0.75);
    expect(s.metrics.nFills).toBe(12);
    expect(s.metrics.nActions).toBe(0); // unchanged default
  });

  it('accumulates events', () => {
    const store = useExperimentStore.getState();
    store.addEvent({ event: 'tick_started', data: { tick: 1 } });
    store.addEvent({ event: 'tick_finished', data: { tick: 1 } });
    expect(useExperimentStore.getState().events.length).toBe(2);
  });

  it('accumulates tick metrics in arrival order', () => {
    const store = useExperimentStore.getState();
    store.addTickMetrics({ tick: 0, yes_mid: 0.5, no_mid: 0.5, parity_gap: 0, n_fills: 2, ret: 0 });
    store.addTickMetrics({ tick: 1, yes_mid: 0.6, no_mid: 0.4, parity_gap: 0, n_fills: 3, ret: 0.1 });
    const tm = useExperimentStore.getState().tickMetrics;
    expect(tm.length).toBe(2);
    expect(tm[1].yes_mid).toBe(0.6);
  });

  it('groups agent snapshots by agent id into tick-ordered histories', () => {
    const store = useExperimentStore.getState();
    const snap = (tick: number, agent_id: number, pnl: number): import('../types').AgentSnapshot => ({
      tick, agent_id, persona: 'alpha', cash: 1000, cash_reserved: 0,
      pos_yes: 0, pos_no: 0, belief_yes: null, belief_conf: null, pnl,
    });
    store.addAgentSnapshots([snap(0, 0, 1), snap(0, 1, -2)]);
    store.addAgentSnapshots([snap(1, 0, 3), snap(1, 1, -1)]);
    const snaps = useExperimentStore.getState().agentSnapshots;
    expect(Object.keys(snaps).length).toBe(2);
    expect(snaps[0].length).toBe(2);
    expect(snaps[0][1].pnl).toBe(3);
    expect(snaps[1][1].pnl).toBe(-1);
  });

  it('routes forum events into store via applyEvent and clears on reset', () => {
    const store = useExperimentStore.getState();
    applyEvent(store, 'forum_post', { tick: 0, author_id: 1, post_id: 10, content: 'hello' });
    applyEvent(store, 'forum_comment', { tick: 1, author_id: 2, post_id: 10, comment_id: 100, content: 'reply' });
    applyEvent(store, 'forum_follow', { tick: 1, agent_id: 2, target_id: 1 });
    let s = useExperimentStore.getState();
    expect(s.forumPosts.length).toBe(1);
    expect(s.forumPosts[0].post_id).toBe(10);
    expect(s.forumComments.length).toBe(1);
    expect(s.forumComments[0].comment_id).toBe(100);
    expect(s.follows.length).toBe(1);
    expect(s.follows[0].target_id).toBe(1);
    useExperimentStore.getState().resetSimulation();
    s = useExperimentStore.getState();
    expect(s.forumPosts.length).toBe(0);
    expect(s.forumComments.length).toBe(0);
    expect(s.follows.length).toBe(0);
  });

  it('clears tick metrics and snapshots on reset', () => {
    const store = useExperimentStore.getState();
    store.addTickMetrics({ tick: 0, yes_mid: 0.5, no_mid: 0.5, parity_gap: 0, n_fills: 0, ret: 0 });
    store.addAgentSnapshots([{
      tick: 0, agent_id: 0, persona: 'a', cash: 0, cash_reserved: 0,
      pos_yes: 0, pos_no: 0, belief_yes: null, belief_conf: null, pnl: 0,
    }]);
    store.resetSimulation();
    const s = useExperimentStore.getState();
    expect(s.tickMetrics.length).toBe(0);
    expect(Object.keys(s.agentSnapshots).length).toBe(0);
  });

  it('produces equivalent critical state for live and replay event application', () => {
    const events: Array<{ kind: string; data: Record<string, unknown> }> = [
      { kind: 'run_started', data: { slug: 'equivalence-market' } },
      { kind: 'env_ready', data: { yes_mid_post_seed: 0.52, n_ticks: 2 } },
      { kind: 'tick_started', data: { tick: 0 } },
      {
        kind: 'agent_decision',
        data: {
          agent_id: 7,
          tick: 0,
          persona_type: 'alpha',
          order_type: 'limit',
          side: 'buy',
          outcome: 'YES',
          price: 0.54,
          size_usd: 25,
          reasoning: 'signal',
          api_latency_ms: 80,
        },
      },
      {
        kind: 'tick_metrics',
        data: {
          tick: 0,
          yes_mid: 0.54,
          no_mid: 0.46,
          parity_gap: 0,
          n_fills: 1,
          ret: 0.02,
        },
      },
      {
        kind: 'agent_snapshots',
        data: {
          tick: 0,
          agents: [{
            tick: 0,
            agent_id: 7,
            persona: 'alpha',
            cash: 975,
            cash_reserved: 0,
            pos_yes: 25,
            pos_no: 0,
            belief_yes: 0.6,
            belief_conf: 0.8,
            pnl: 1.5,
          }],
        },
      },
      {
        kind: 'tick_finished',
        data: { tick: 0, yes_mid: 0.54, n_fills: 1, n_actions: 1, elapsed_s: 0.2 },
      },
      {
        kind: 'settled',
        data: { yes_mid_final: 0.58, n_fills: 2, n_actions: 2 },
      },
    ];

    const applySequence = () => {
      for (const event of events) {
        applyEvent(useExperimentStore.getState(), event.kind, event.data);
      }
      const state = useExperimentStore.getState();
      return {
        events: state.events,
        decisions: state.decisions.map((decision) => ({
          agent_id: decision.agent_id,
          tick: decision.tick,
          persona_type: decision.persona_type,
          order_type: decision.order_type,
          side: decision.side,
          outcome: decision.outcome,
          price: decision.price,
          size_usd: decision.size_usd,
          reasoning: decision.reasoning,
          api_latency_ms: decision.api_latency_ms,
          api_error: decision.api_error,
        })),
        metrics: state.metrics,
        tickMetrics: state.tickMetrics,
        agentSnapshots: state.agentSnapshots,
        logMessages: state.tickLog.map((entry) => ({
          label: entry.label,
          msg: entry.msg,
          kind: entry.kind,
        })),
      };
    };

    const liveState = applySequence();
    useExperimentStore.getState().resetSimulation();
    const replayState = applySequence();

    expect(replayState).toEqual(liveState);
    expect(replayState.metrics).toMatchObject({
      yesMid: 0.58,
      nFills: 2,
      nActions: 2,
      currentTick: 0,
      totalTicks: 2,
    });
    expect(replayState.decisions).toHaveLength(1);
    expect(replayState.tickMetrics).toHaveLength(1);
    expect(replayState.agentSnapshots[7]).toHaveLength(1);
  });
});
