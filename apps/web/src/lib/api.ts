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

  // Settings
  getApiSettings: () =>
    fetchJson<{ settings: import('../types').ApiSettings }>('/api/v1/settings/api'),

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

  // Providers
  listProviders: () =>
    fetchJson<{ providers: import('../types').ProviderInfo[] }>('/api/v1/providers'),
};
