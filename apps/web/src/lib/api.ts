const API_BASE = import.meta.env.VITE_API_BASE || '';

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${txt}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  // Markets
  listMarkets: (params?: {
    q?: string; live_only?: boolean; limit?: number; category?: string; offset?: number;
  }) => {
    const url = new URL('/api/v1/markets', window.location.origin);
    if (params?.q) url.searchParams.set('q', params.q);
    if (params?.live_only) url.searchParams.set('live_only', '1');
    if (params?.limit) url.searchParams.set('limit', String(params.limit));
    if (params?.category) url.searchParams.set('category', params.category);
    if (params?.offset) url.searchParams.set('offset', String(params.offset));
    return fetchJson<{
      markets: import('../types').Market[];
      offset?: number;
      limit?: number;
      hasMore?: boolean;
    }>(url.pathname + url.search);
  },

  getMarket: (slug: string) =>
    fetchJson<{ market: import('../types').MarketDetail }>(`/api/v1/markets/${slug}`),

  // Sibling sub-markets sharing an event (for multi-market event detail views).
  getEventMarkets: (eventSlug: string) =>
    fetchJson<{ markets: import('../types').Market[] }>(
      `/api/v1/markets/events/${encodeURIComponent(eventSlug)}`,
    ),

  getCategories: () =>
    fetchJson<{ categories: string[] }>('/api/v1/markets/categories'),

  // Experiments
  listExperiments: (params?: {
    status?: string;
    slug?: string;
    limit?: number;
    offset?: number;
  }) => {
    const url = new URL('/api/v1/experiments', window.location.origin);
    if (params?.status) url.searchParams.set('status', params.status);
    if (params?.slug) url.searchParams.set('slug', params.slug);
    if (params?.limit) url.searchParams.set('limit', String(params.limit));
    if (params?.offset) url.searchParams.set('offset', String(params.offset));
    return fetchJson<{
      experiments: import('../types').Experiment[];
      total: number;
      limit: number;
      offset: number;
    }>(url.pathname + url.search);
  },

  searchExperiments: (q: string, limit?: number) => {
    const url = new URL('/api/v1/experiments/search', window.location.origin);
    url.searchParams.set('q', q);
    if (limit) url.searchParams.set('limit', String(limit));
    return fetchJson<{ experiments: import('../types').Experiment[] }>(url.pathname + url.search);
  },

  getExperimentStats: () =>
    fetchJson<{
      total_runs: number;
      running_count: number;
      avg_agents: number;
      avg_ticks: number;
    }>('/api/v1/experiments/stats'),

  getExperiment: (id: string) =>
    fetchJson<{ experiment: import('../types').Experiment }>(`/api/v1/experiments/${id}`),

  createExperiment: (config: import('../types').ExperimentConfig) =>
    fetchJson<{ run_id: string }>('/api/v1/experiments', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  cancelExperiment: (id: string) =>
    fetchJson<{ cancelled: boolean }>(`/api/v1/experiments/${id}/cancel`, { method: 'POST' }),

  // Pause a running experiment: the backend checkpoints at the next tick
  // boundary and flips status to 'paused'.
  pauseExperiment: (id: string) =>
    fetchJson<{ paused: boolean; checkpoint_path?: string | null; message?: string }>(
      `/api/v1/experiments/${id}/pause`,
      { method: 'POST' },
    ),

  // Resume a paused experiment from its stored checkpoint (same id).
  resumeExperiment: (id: string) =>
    fetchJson<{ run_id: string; resumed: boolean }>(
      `/api/v1/experiments/${id}/resume`,
      { method: 'POST' },
    ),

  // Full recorded event history of a finished run, for the replay player.
  // Throws (HTTP 404) when the run has no recorded event log.
  getReplay: (id: string) =>
    fetchJson<{
      events: { kind: string; data: Record<string, unknown> }[];
      total: number;
    }>(`/api/v1/experiments/${id}/replay`),

  // Settings
  // Response carries api_key_set (boolean) and never the plaintext api_key.
  getApiSettings: () =>
    fetchJson<{ settings: import('../types').ApiSettings }>('/api/v1/settings/api'),

  // Send the plaintext api_key only when the user entered a new one; omit it to
  // keep the existing stored key unchanged.
  updateApiSettings: (settings: import('../types').ApiSettings) =>
    fetchJson<{ settings: import('../types').ApiSettings }>('/api/v1/settings/api', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),

  // Settings test
  testConnection: (settings: import('../types').ApiSettings) =>
    fetchJson<{ ok: boolean; message: string }>('/api/v1/settings/test', {
      method: 'POST',
      body: JSON.stringify(settings),
    }),

  // API Keys (named, multi-key store). Responses never include plaintext keys.
  listApiKeys: () =>
    fetchJson<{ keys: import('../types').ApiKey[] }>('/api/v1/keys'),

  createApiKey: (input: {
    name: string;
    provider: string;
    api_key: string;
    base_url?: string;
    model?: string;
  }) =>
    fetchJson<{ id: number; keys: import('../types').ApiKey[] }>('/api/v1/keys', {
      method: 'POST',
      body: JSON.stringify(input),
    }),

  deleteApiKey: (id: number) =>
    fetchJson<{ deleted: boolean; keys: import('../types').ApiKey[] }>(
      `/api/v1/keys/${id}`,
      { method: 'DELETE' },
    ),

  // Providers
  listProviders: () =>
    fetchJson<{ providers: import('../types').ProviderInfo[] }>('/api/v1/providers'),

  // Fetch a provider's available models live via its /models endpoint.
  // Falls back to the static catalog (source: 'catalog') when no key is set,
  // the provider is litellm-native, or the upstream fetch fails.
  listProviderModels: (providerId: string) =>
    fetchJson<{ models: string[]; source: 'live' | 'catalog'; message?: string }>(
      `/api/v1/providers/${encodeURIComponent(providerId)}/models`,
    ),
};
