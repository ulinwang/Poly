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
  // Multi-market events: event_slug is the shared event id, event_title is the
  // parent event name (e.g. "What will happen before GTA VI?"), group_title is
  // this sub-market's outcome label (e.g. "50+ bps decrease"). Null otherwise.
  event_slug?: string | null;
  event_title?: string | null;
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

export interface ProviderInfo {
  id: string;
  name: string;
  models: string[];
  requires_base_url: boolean;
  base_url?: string;
}
