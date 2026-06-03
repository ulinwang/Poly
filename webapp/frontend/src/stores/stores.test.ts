import { describe, it, expect, beforeEach } from 'vitest';
import { useSettingsStore, useMarketStore, useExperimentStore } from './index';

// Zustand stores are singletons — reset between tests by mutating state directly
describe('Settings store', () => {
  beforeEach(() => {
    useSettingsStore.setState({
      apiSettings: { provider: 'deepseek', model: 'deepseek-chat', api_key: '', temperature: 0.7, max_tokens: 2048 },
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
});
