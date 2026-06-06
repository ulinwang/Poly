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
  appendMarkets: (markets: Market[]) => void;
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
  appendMarkets: (markets) => set((s) => {
    // De-dup by slug so overlapping/repeated Gamma pages don't create
    // duplicate cards (and duplicate React keys).
    const seen = new Set(s.markets.map((m) => m.slug));
    const fresh = markets.filter((m) => !seen.has(m.slug));
    return { markets: [...s.markets, ...fresh] };
  }),
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

// Lightweight localStorage persistence for UI preferences (no extra deps).
function readBool(key: string, fallback: boolean): boolean {
  if (typeof localStorage === 'undefined') return fallback;
  const raw = localStorage.getItem(key);
  return raw === null ? fallback : raw === '1';
}
function writeBool(key: string, value: boolean): void {
  if (typeof localStorage !== 'undefined') localStorage.setItem(key, value ? '1' : '0');
}

export const useSettingsStore = create<SettingsState>((set) => ({
  apiSettings: defaultApiSettings,
  darkMode: readBool('poly.darkMode', false),
  sidebarCollapsed: readBool('poly.sidebarCollapsed', false),
  setApiSettings: (apiSettings) => set({ apiSettings }),
  updateApiSettings: (partial) => set((s) => ({
    apiSettings: { ...s.apiSettings, ...partial },
  })),
  toggleDarkMode: () => set((s) => {
    const next = !s.darkMode;
    if (typeof document !== 'undefined') {
      document.documentElement.classList.toggle('dark', next);
    }
    writeBool('poly.darkMode', next);
    return { darkMode: next };
  }),
  toggleSidebar: () => set((s) => {
    const next = !s.sidebarCollapsed;
    writeBool('poly.sidebarCollapsed', next);
    return { sidebarCollapsed: next };
  }),
}));
