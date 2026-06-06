import { describe, it, expect, beforeEach } from 'vitest';
import { useSettingsStore, useMarketStore, useExperimentStore } from './index';

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
});
