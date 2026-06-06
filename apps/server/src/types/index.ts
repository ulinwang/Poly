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
   * Named API key (api_keys.id) to use for this run. When omitted, the default
   * api_settings configuration is used instead.
   */
  api_key_id?: number;
  /** RNG seed handed to the sim core for reproducible runs. Defaults to 0. */
  seed?: number;
  /** LLM sampling temperature. Defaults to 0. */
  temperature?: number;
}

export interface ExperimentRow {
  id: string;
  slug: string;
  n_agents: number;
  n_ticks: number;
  persona_set: string;
  api_settings_id?: number | null;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  result_summary?: string | null;
  created_at?: string | null;
  final_yes_mid?: number | null;
  total_fills?: number | null;
  total_actions?: number | null;
  avg_tick_time_ms?: number | null;
  /** Pickle checkpoint path written on pause; consumed on resume. */
  checkpoint_path?: string | null;
  /** RNG seed used for the run; null for legacy rows predating this column. */
  seed?: number | null;
  /** Named API key (api_keys.id) used for the run; null when default settings. */
  api_key_id?: number | null;
}

export interface Experiment {
  id: string;
  slug: string;
  n_agents: number;
  n_ticks: number;
  persona_set: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  elapsed_s?: number;
  result_summary?: Record<string, unknown> | null;
  /** RNG seed used for the run, when known. */
  seed?: number | null;
}

export interface ApiSettings {
  id?: number;
  provider: 'openai' | 'anthropic' | 'deepseek' | 'kimi' | 'custom';
  model: string;
  /**
   * Plaintext API key. Optional: present on incoming requests and on the
   * internal decrypted view, but never included in responses to the client.
   */
  api_key?: string;
  /** Whether an API key is stored. Used in responses instead of the key. */
  api_key_set?: boolean;
  base_url?: string;
  temperature: number;
  max_tokens: number;
}

/**
 * Safe view of a stored named API key. Never includes the plaintext key; only
 * a masked preview (e.g. "sk-…a1b2") for display.
 */
export interface ApiKey {
  id: number;
  name: string;
  provider: string;
  base_url?: string;
  model?: string;
  created_at: string;
  /** Masked preview of the key, e.g. "sk-…a1b2". Never the full secret. */
  key_masked: string;
}

/**
 * Internal decrypted view of a named API key. Used only to spawn the sim
 * subprocess; never returned to the client.
 */
export interface ApiKeyDecrypted {
  id: number;
  name: string;
  provider: string;
  api_key: string;
  base_url?: string;
  model?: string;
}

export interface ProviderInfo {
  id: string;
  name: string;
  models: string[];
  requires_base_url: boolean;
  base_url?: string;
}
