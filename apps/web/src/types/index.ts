export interface Market {
  slug: string;
  question: string;
  condition_id: string;
  volume: number;
  is_live: boolean;
  end_date_iso: string | null;
  n_holders: number | null;
  categories?: string[];
  icon_url?: string;
  // Shared event slug for multi-market events; group_title is this sub-market's
  // outcome label (e.g. "50+ bps decrease"). Null for standalone markets.
  event_slug?: string | null;
  group_title?: string | null;
}

export interface MarketDetail extends Market {
  tick_size: number;
  taker_fee_bps: number;
  description?: string;
  yes_token_id: string;
  no_token_id: string;
  outcomes: string[];
  event_slug?: string | null;
}

export interface ExperimentConfig {
  slug: string;
  n_agents: number;
  n_ticks: number;
  persona_set: 'archetype' | 'calibrated' | 'no_signal';
  api_settings_id?: number;
}

export interface Experiment {
  id: string;
  slug: string;
  n_agents: number;
  n_ticks: number;
  persona_set: string;
  status: 'queued' | 'running' | 'completed' | 'cancelled' | 'error';
  started_at: string;
  finished_at: string | null;
  elapsed_s: number;
  result_summary?: Record<string, unknown>;
}

export interface ApiSettings {
  id?: number;
  provider: 'openai' | 'anthropic' | 'deepseek' | 'kimi' | 'custom';
  model: string;
  /**
   * Plaintext API key. Optional: only sent to the server when the user enters a
   * new key. The server never returns it.
   */
  api_key?: string;
  /** Whether a key is stored server-side. Present on responses. */
  api_key_set: boolean;
  base_url?: string;
  temperature: number;
  max_tokens: number;
}

export interface ProviderInfo {
  id: string;
  name: string;
  models: string[];
  requires_base_url: boolean;
  base_url?: string;
}

export interface SimulationEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface AgentDecision {
  id: number;
  agent_id: number;
  tick: number;
  persona_type: string;
  order_type: string;
  side?: string;
  outcome?: string;
  price: number;
  size_usd: number;
  reasoning: string;
  api_latency_ms: number;
  api_error?: string;
}

export interface TickLogEntry {
  id: number;
  time: string;
  label: string;
  msg: string;
  kind: 'info' | 'warn' | 'error';
}

/**
 * Macro (market-price) snapshot for a single tick.
 * Mirrors sim/evaluation/schema.py::TickMetrics. Streamed as `tick_metrics`.
 */
export interface TickMetrics {
  tick: number;
  yes_mid: number;
  no_mid: number;
  /** Deviation from the YES+NO=1 arbitrage parity; large |gap| ⇒ inefficiency. */
  parity_gap: number;
  /** Fills that happened during this tick. */
  n_fills: number;
  /** YES-mid change vs the previous tick (per-tick return). */
  ret: number;
}

/**
 * Micro (single-agent) snapshot for a single tick.
 * Mirrors sim/evaluation/schema.py::AgentSnapshot. Streamed inside
 * `agent_snapshots` (one envelope per tick carrying every agent's row).
 */
export interface AgentSnapshot {
  tick: number;
  agent_id: number;
  persona: string;
  cash: number;
  cash_reserved: number;
  pos_yes: number;
  pos_no: number;
  /** Agent's stated posterior P(YES), if set (else null). */
  belief_yes: number | null;
  /** Agent's stated confidence, if set (else null). */
  belief_conf: number | null;
  /** Mark-to-market PnL vs initial capital at the current mids. */
  pnl: number;
}

export interface SimulationMetrics {
  yesMid: number;
  yesMidHistory: number[];
  nFills: number;
  nActions: number;
  currentTick: number | null;
  totalTicks: number;
  lastTickElapsed: number;
}
