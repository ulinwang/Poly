import type { FastifyInstance } from 'fastify';
import { providerInfoList, PROVIDER_CATALOG } from '../providers.js';
import { getApiSettingsDecrypted } from '../db/settings.js';

interface ModelsResponse {
  models: string[];
  source: 'live' | 'catalog';
  message?: string;
}

// Simple in-memory cache for live /models results, keyed by provider id.
// Avoids hammering the upstream endpoint on repeated refreshes.
const MODELS_CACHE_TTL_MS = 30_000;
const modelsCache = new Map<string, { expires: number; data: ModelsResponse }>();

export default async function providersRoutes(app: FastifyInstance) {
  app.get('', async () => {
    return { providers: providerInfoList() };
  });

  // Dynamically list a provider's available models via its OpenAI-compatible
  // `GET {base_url}/models` endpoint. Falls back to the static catalog when the
  // provider is litellm-native (no base_url), has no key, or the fetch fails.
  // The API key is read from stored settings, or overridden via ?api_key= for
  // the "testing before save" case. The key is never logged.
  app.get<{ Params: { id: string }; Querystring: { api_key?: string } }>(
    '/:id/models',
    async (req): Promise<ModelsResponse> => {
      const { id } = req.params;
      const entry = PROVIDER_CATALOG.find((p) => p.id === id);
      const catalogModels = entry?.models ?? [];

      // Unknown provider id: just echo an empty catalog.
      if (!entry) {
        return { models: catalogModels, source: 'catalog', message: 'unknown provider' };
      }

      // litellm-native providers (no OpenAI-compatible base URL, e.g. anthropic):
      // there is no /models endpoint to query, so serve the static catalog.
      if (!entry.base_url) {
        return {
          models: catalogModels,
          source: 'catalog',
          message: 'provider has no OpenAI-compatible endpoint; using catalog',
        };
      }

      const queryKey = req.query?.api_key;
      const apiKey = queryKey || getApiSettingsDecrypted()?.api_key || '';
      if (!apiKey) {
        return { models: catalogModels, source: 'catalog', message: 'no api key' };
      }

      // Serve from cache only when a stored key is used (not a per-request
      // override), so an override always reflects the key it was given.
      const useCache = !queryKey;
      if (useCache) {
        const cached = modelsCache.get(id);
        if (cached && cached.expires > Date.now()) {
          return cached.data;
        }
      }

      try {
        const resp = await fetch(`${entry.base_url}/models`, {
          headers: { Authorization: `Bearer ${apiKey}` },
        });
        if (!resp.ok) {
          return {
            models: catalogModels,
            source: 'catalog',
            message: `HTTP ${resp.status}; using catalog`,
          };
        }
        const json = (await resp.json()) as { data?: Array<{ id?: string }> };
        const models = (json.data ?? [])
          .map((m) => m.id)
          .filter((m): m is string => typeof m === 'string' && m.length > 0);
        if (models.length === 0) {
          return {
            models: catalogModels,
            source: 'catalog',
            message: 'endpoint returned no models; using catalog',
          };
        }
        const data: ModelsResponse = { models, source: 'live' };
        if (useCache) {
          modelsCache.set(id, { expires: Date.now() + MODELS_CACHE_TTL_MS, data });
        }
        return data;
      } catch (err) {
        return {
          models: catalogModels,
          source: 'catalog',
          message: `fetch failed: ${(err as Error).message}; using catalog`,
        };
      }
    },
  );
}
