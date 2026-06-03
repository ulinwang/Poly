import { create } from 'zustand';
import type {
  Market, Experiment, ApiSettings, SimulationEvent,
  AgentDecision, TickLogEntry, SimulationMetrics,
} from '../types';

interface MarketState {
  markets: Market[];
  selectedSlug: string | null;
  category: string;
  searchQuery: string;
  loading: boolean;
  error: string | null;
  setMarkets: (markets: Market[]) => void;
  selectMarket: (slug: string | null) => void;
  setCategory: (category: string) => void;
  setSearchQuery: (q: string) => void;
  setLoading: (v: boolean) => void;
  setError: (e: string | null) => void;
}

export const useMarketStore = create<MarketState>((set) => ({
  markets: [],
  selectedSlug: null,
  category: 'All',
  searchQuery: '',
  loading: false,
  error: null,
  setMarkets: (markets) => set({ markets }),
  selectMarket: (slug) => set({ selectedSlug: slug }),
  setCategory: (category) => set({ category }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));

interface ExperimentState {
  experiments: Experiment[];
  activeId: string | null;
  events: SimulationEvent[];
  decisions: AgentDecision[];
  tickLog: TickLogEntry[];
  metrics: SimulationMetrics;
  running: boolean;
  error: string | null;
  setExperiments: (experiments: Experiment[]) => void;
  setActiveId: (id: string | null) => void;
  addEvent: (event: SimulationEvent) => void;
  addDecision: (decision: AgentDecision) => void;
  addTickLog: (entry: TickLogEntry) => void;
  setMetrics: (metrics: Partial<SimulationMetrics>) => void;
  setRunning: (v: boolean) => void;
  setError: (e: string | null) => void;
  resetSimulation: () => void;
}

export const useExperimentStore = create<ExperimentState>((set) => ({
  experiments: [],
  activeId: null,
  events: [],
  decisions: [],
  tickLog: [],
  metrics: {
    yesMid: 0.5,
    yesMidHistory: [],
    nFills: 0,
    nActions: 0,
    currentTick: null,
    totalTicks: 0,
    lastTickElapsed: 0,
  },
  running: false,
  error: null,
  setExperiments: (experiments) => set({ experiments }),
  setActiveId: (activeId) => set({ activeId }),
  addEvent: (event) => set((s) => ({ events: [...s.events, event] })),
  addDecision: (decision) => set((s) => {
    const next = [...s.decisions, decision];
    if (next.length > 400) next.shift();
    return { decisions: next };
  }),
  addTickLog: (entry) => set((s) => {
    const next = [...s.tickLog, entry];
    if (next.length > 300) next.shift();
    return { tickLog: next };
  }),
  setMetrics: (metrics) => set((s) => ({ metrics: { ...s.metrics, ...metrics } })),
  setRunning: (running) => set({ running }),
  setError: (error) => set({ error }),
  resetSimulation: () => set({
    events: [],
    decisions: [],
    tickLog: [],
    metrics: {
      yesMid: 0.5,
      yesMidHistory: [],
      nFills: 0,
      nActions: 0,
      currentTick: null,
      totalTicks: 0,
      lastTickElapsed: 0,
    },
    running: false,
    error: null,
  }),
}));

interface SettingsState {
  apiSettings: ApiSettings;
  darkMode: boolean;
  sidebarCollapsed: boolean;
  setApiSettings: (settings: ApiSettings) => void;
  updateApiSettings: (partial: Partial<ApiSettings>) => void;
  toggleDarkMode: () => void;
  toggleSidebar: () => void;
}

const defaultApiSettings: ApiSettings = {
  provider: 'deepseek',
  model: 'deepseek-chat',
  api_key: '',
  temperature: 0.7,
  max_tokens: 2048,
};

export const useSettingsStore = create<SettingsState>((set) => ({
  apiSettings: defaultApiSettings,
  darkMode: false,
  sidebarCollapsed: false,
  setApiSettings: (apiSettings) => set({ apiSettings }),
  updateApiSettings: (partial) => set((s) => ({
    apiSettings: { ...s.apiSettings, ...partial },
  })),
  toggleDarkMode: () => set((s) => ({ darkMode: !s.darkMode })),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));
