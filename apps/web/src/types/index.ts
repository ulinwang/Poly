// A single market outcome label paired with its live probability (0..1), or
// null when no quote is available. For binary markets this is Yes/No; for
// match/multi-choice markets these are the real option names (e.g. "G2").
export interface OutcomeEntry {
  label: string;
  price: number | null;
}

export interface Market {
  slug: string;
  question: string;
  condition_id: string;
  volume: number;
  is_live: boolean;
  end_date_iso: string | null;
  n_holders: number | null;
  categories?: string[];
  // Real outcome labels + live prices, in API order. Binary markets pair
  // Yes/No; multi-result markets carry team/option names. May be empty when the
  // upstream feed omitted outcomes.
  outcomes_list?: OutcomeEntry[];
  // True only when outcomes are exactly ["Yes","No"] (case-insensitive). When
  // false, the market is multi-result and must not be rendered as Yes/No.
  is_binary?: boolean;
  icon_url?: string;
  // Parent event thumbnail (used for grouped event cards). Null if absent.
  event_icon?: string | null;
  // Live YES probability (0..1) from Polymarket, or null when no quote exists.
  yes_price?: number | null;
  // 24h YES price change (signed), or null when unavailable.
  price_change_24h?: number | null;
  // Multi-market events: event_slug is the shared event id, event_title is the
  // parent event name (e.g. "What will happen before GTA VI?"), group_title is
  // this sub-market's outcome label (e.g. "50+ bps decrease"). Null otherwise.
  event_slug?: string | null;
  event_title?: string | null;
  event_description?: string | null;
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

// One selectable outcome inside an event summary. For a multi-result event this
// is a single sub-market: `label` is its groupItemTitle (or question), `price`
// is its YES probability (0..1, or null when no quote), and `slug` is that
// sub-market's slug (used to deep-link into the detail page).
export interface EventOutcomeSummary {
  label: string;
  price: number | null;
  slug: string;
}

// Server-grouped view of a Polymarket event for the browse page. Replaces the
// old client-side groupByEvent so pagination works across pages. A single
// binary market event has is_single=true and renders as an ordinary Yes/No
// card; everything else renders as a multi-outcome event card.
export interface EventSummary {
  event_slug: string;
  title: string;
  icon_url?: string;
  description?: string;
  volume: number;
  categories: string[];
  n_outcomes: number;
  // Slug to route to when the card is clicked (first / highest-volume
  // sub-market). The detail page surfaces the sibling outcomes from there.
  primary_slug: string;
  // True only when the event holds exactly one binary (Yes/No) sub-market.
  is_single: boolean;
  outcomes: EventOutcomeSummary[];
}

export interface ExperimentConfig {
  slug: string;
  n_agents: number;
  n_ticks: number;
  persona_set: 'archetype' | 'calibrated' | 'no_signal';
  api_settings_id?: number;
  /**
   * Named API key (ApiKey.id) to use for this run. Omit to use the default
   * API settings configured under Settings.
   */
  api_key_id?: number;
  /** RNG seed handed to the sim core for reproducible runs. Defaults to 0. */
  seed?: number;
  /** LLM sampling temperature. Defaults to 0. */
  temperature?: number;
}

export interface Experiment {
  id: string;
  slug: string;
  n_agents: number;
  n_ticks: number;
  persona_set: string;
  status: 'queued' | 'running' | 'paused' | 'completed' | 'cancelled' | 'error';
  started_at: string;
  finished_at: string | null;
  elapsed_s: number;
  result_summary?: Record<string, unknown>;
  /** RNG seed used for the run, when known. */
  seed?: number | null;
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

/**
 * Safe view of a stored named API key. The server never returns the plaintext
 * key, only a masked preview.
 */
export interface ApiKey {
  id: number;
  name: string;
  provider: string;
  base_url?: string;
  model?: string;
  created_at: string;
  /** Masked preview, e.g. "sk-…a1b2". */
  key_masked: string;
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

// ── Forum / social (Forum & Social tabs) ─────────────────────────────
/**
 * A forum post authored by an agent during the run. Mirrors the backend
 * `forum_post` event: { tick, author_id, post_id, content }.
 */
export interface ForumPost {
  tick: number;
  author_id: number;
  post_id: number;
  content: string;
}

/**
 * A comment on a forum post. Mirrors the backend `forum_comment` event:
 * { tick, author_id, post_id, comment_id, content }.
 */
export interface ForumComment {
  tick: number;
  author_id: number;
  post_id: number;
  comment_id: number;
  content: string;
}

/**
 * A directed follow edge between two agents. Mirrors the backend
 * `forum_follow` event: { tick, agent_id, target_id } where agent_id follows
 * target_id.
 */
export interface FollowEdge {
  tick: number;
  agent_id: number;
  target_id: number;
}

// ── Agent introspection (Agent tab) ──────────────────────────────────
export interface AgentToolParamProperty {
  type?: string;
  description?: string;
  enum?: string[];
  minimum?: number;
  maximum?: number;
  maxLength?: number;
}

export interface AgentTool {
  name: string;
  description: string;
  parameters: {
    type?: string;
    properties?: Record<string, AgentToolParamProperty>;
    required?: string[];
  };
}

export interface AgentPromptTemplate {
  title: string;
  description: string;
  source: string;
  template: string;
}

export interface AgentInfo {
  tools: AgentTool[];
  prompt_templates: Record<string, AgentPromptTemplate>;
  /** Present only when the introspection spawn failed. */
  message?: string;
}

// ── On-chain market analysis (Data analysis tab) ─────────────────────
export interface AnalysisVolumePoint {
  date: string;
  volume: number;
  trades: number;
}

export interface AnalysisTopWallet {
  wallet: string;
  notional: number;
  share: number;
}

export interface MarketAnalysis {
  available: boolean;
  message?: string;
  slug?: string;
  condition_id?: string;
  question?: string;
  outcomes?: string[];
  winning_idx?: number;
  metrics?: {
    n_trades: number;
    total_notional: number;
    unique_wallets: number;
    first_trade_ts: number | null;
    last_trade_ts: number | null;
  };
  volume_series?: AnalysisVolumePoint[];
  top_wallets?: AnalysisTopWallet[];
  concentration?: {
    top1_share: number;
    top5_share: number;
    top10_share: number;
  };
  holders?: {
    n_holders: number;
    yes_holders: number;
    no_holders: number;
  } | null;
}
