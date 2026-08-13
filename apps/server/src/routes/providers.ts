import type { FastifyInstance } from 'fastify';
import { providerInfoList, PROVIDER_CATALOG } from '../providers.js';
import { getApiSettingsDecrypted } from '../db/settings.js';
import { normalizeLlmBaseUrl, validateOutboundLlmUrl } from '../security/outbound-url.js';

interface ModelsResponse {
  models: string[];
  source: 'live' | 'catalog';
  message?: string;
  refreshed_at?: string;
}

// Simple in-memory cache for live /models results, keyed by provider id.
// Avoids hammering the upstream endpoint on repeated refreshes.
const MODELS_CACHE_TTL_MS = 30_000;
const modelsCache = new Map<string, { expires: number; data: ModelsResponse }>();

interface DiscoverModelsBody {
  provider: string;
  base_url?: string;
  api_key?: string;
}

function sameEndpoint(left?: string, right?: string): boolean {
  if (!left || !right) return left === right;
  try {
    return normalizeLlmBaseUrl(left) === normalizeLlmBaseUrl(right);
  } catch {
    return false;
  }
}

async function discoverModels(body: DiscoverModelsBody): Promise<ModelsResponse> {
  const entry = PROVIDER_CATALOG.find((p) => p.id === body.provider);
  const catalogModels = entry?.models ?? [];
  const requestedBaseUrl = body.base_url?.trim() || entry?.base_url;
  if (!requestedBaseUrl) {
    return {
      models: catalogModels,
      source: 'catalog',
      message: entry ? 'provider has no OpenAI-compatible endpoint; using catalog' : 'base URL required',
    };
  }

  const suppliedApiKey = body.api_key?.trim() || '';
  const stored = getApiSettingsDecrypted();
  const storedBaseUrl = stored?.base_url || (stored ? PROVIDER_CATALOG.find((p) => p.id === stored.provider)?.base_url : undefined);
  const mayReuseStoredKey = Boolean(
    stored && stored.provider === body.provider && sameEndpoint(storedBaseUrl, requestedBaseUrl),
  );
  const apiKey = suppliedApiKey || (mayReuseStoredKey ? stored?.api_key || '' : '');
  if (!apiKey) {
    return { models: catalogModels, source: 'catalog', message: 'no api key' };
  }

  try {
    const safeBaseUrl = await validateOutboundLlmUrl(requestedBaseUrl);
    const cacheKey = `${body.provider}:${safeBaseUrl}`;
    const cached = !suppliedApiKey ? modelsCache.get(cacheKey) : undefined;
    if (cached && cached.expires > Date.now()) return cached.data;

    const resp = await fetch(`${safeBaseUrl}/models`, {
      redirect: 'error',
      signal: AbortSignal.timeout(10_000),
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    if (!resp.ok) {
      return { models: catalogModels, source: 'catalog', message: `HTTP ${resp.status}; using catalog` };
    }
    const json = (await resp.json()) as { data?: Array<{ id?: string }> };
    const models = [...new Set((json.data ?? [])
      .map((model) => model.id)
      .filter((model): model is string => typeof model === 'string' && model.length > 0))]
      .sort((a, b) => a.localeCompare(b));
    if (models.length === 0) {
      return { models: catalogModels, source: 'catalog', message: 'endpoint returned no models; using catalog' };
    }
    const data: ModelsResponse = {
      models,
      source: 'live',
      refreshed_at: new Date().toISOString(),
    };
    if (!suppliedApiKey) {
      modelsCache.set(cacheKey, { expires: Date.now() + MODELS_CACHE_TTL_MS, data });
    }
    return data;
  } catch (error) {
    return {
      models: catalogModels,
      source: 'catalog',
      message: `fetch failed: ${(error as Error).message}; using catalog`,
    };
  }
}

export default async function providersRoutes(app: FastifyInstance) {
  app.get('', async () => {
    return { providers: providerInfoList(), refreshed_at: new Date().toISOString() };
  });

  // Discover against the values currently being edited in Settings, before
  // they are saved. Keeping the key in a POST body avoids leaking it via URL
  // logs/history and makes provider/model changes update immediately.
  app.post<{ Body: DiscoverModelsBody }>('/models/discover', async (req) => {
    return discoverModels(req.body);
  });

  // Dynamically list a provider's available models via its OpenAI-compatible
  // `GET {base_url}/models` endpoint. Falls back to the static catalog when the
  // provider is litellm-native (no base_url), has no key, or the fetch fails.
  // The API key is read only from encrypted server-side settings. Secrets are
  // deliberately rejected in query strings because URLs are commonly logged.
  app.get<{ Params: { id: string }; Querystring: { api_key?: string } }>(
    '/:id/models',
    async (req, reply): Promise<ModelsResponse | { message: string }> => {
      if (req.query?.api_key !== undefined) {
        reply.status(400);
        return { message: 'API keys must not be sent in query strings' };
      }
      return discoverModels({ provider: req.params.id });
    },
  );
}
