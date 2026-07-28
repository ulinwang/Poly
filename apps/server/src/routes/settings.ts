import type { FastifyInstance } from 'fastify';
import { getApiSettings, getApiSettingsDecrypted, saveApiSettings } from '../db/settings.js';
import { providerBaseUrl } from '../providers.js';
import { normalizeLlmBaseUrl, validateOutboundLlmUrl } from '../security/outbound-url.js';
import type { ApiSettings } from '../types/index.js';

const CONNECTION_TEST_TIMEOUT_MS = 10_000;

export default async function settingsRoutes(app: FastifyInstance) {
  app.get('/api', async () => {
    const row = getApiSettings();
    if (!row) {
      const defaults: ApiSettings = {
        provider: 'deepseek',
        model: 'deepseek-chat',
        base_url: undefined,
        temperature: 0.7,
        max_tokens: 2048,
        api_key_set: false,
      };
      return { settings: defaults };
    }
    // getApiSettings() already excludes the plaintext key and sets api_key_set.
    return { settings: row };
  });

  app.put('/api', async (req) => {
    const body = req.body as ApiSettings;
    const payload: Omit<ApiSettings, 'id'> & { id?: number } = {
      provider: body.provider,
      model: body.model,
      // Pass through whatever the client sent; saveApiSettings preserves the
      // existing key when this is empty/undefined.
      api_key: body.api_key,
      base_url: body.base_url,
      temperature: body.temperature,
      max_tokens: body.max_tokens,
    };
    saveApiSettings(payload);
    // Respond with the safe view (no plaintext key).
    return { settings: getApiSettings() };
  });

  app.post('/test', async (req) => {
    const body = req.body as ApiSettings;
    const provider = body.provider;
    const suppliedApiKey = body.api_key?.trim() || '';
    const stored = getApiSettingsDecrypted();
    const apiKey = suppliedApiKey || stored?.api_key || '';
    const model = body.model;
    const baseUrl = body.base_url || providerBaseUrl(provider);

    if (!apiKey) {
      return { ok: false, message: 'API key is required' };
    }
    if (!model) {
      return { ok: false, message: 'Model is required' };
    }

    // A stored secret is bound to the provider and endpoint it was saved with.
    // Callers must supply a new key before probing any other destination.
    if (!suppliedApiKey) {
      const storedBaseUrl = stored?.base_url || (stored ? providerBaseUrl(stored.provider) : undefined);
      let endpointMatches = baseUrl === storedBaseUrl;
      if (baseUrl && storedBaseUrl) {
        try {
          endpointMatches = normalizeLlmBaseUrl(baseUrl) === normalizeLlmBaseUrl(storedBaseUrl);
        } catch {
          endpointMatches = false;
        }
      }
      if (!stored || provider !== stored.provider || !endpointMatches) {
        return {
          ok: false,
          message: 'Enter an API key before testing a different provider or endpoint',
        };
      }
    }

    // litellm-native providers (no OpenAI-compatible base URL) — skip the
    // OpenAI-style live probe; the agent runner reaches them via litellm.
    if (provider === 'anthropic' || !baseUrl) {
      return { ok: true, message: `${provider} selected (routed via litellm; live test skipped)` };
    }

    try {
      const safeBaseUrl = await validateOutboundLlmUrl(baseUrl);
      const resp = await fetch(`${safeBaseUrl}/chat/completions`, {
        method: 'POST',
        redirect: 'error',
        signal: AbortSignal.timeout(CONNECTION_TEST_TIMEOUT_MS),
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model,
          messages: [{ role: 'user', content: 'hi' }],
          max_tokens: 1,
        }),
      });
      if (resp.ok) {
        return { ok: true, message: 'Connection successful' };
      }
      return { ok: false, message: `Provider returned HTTP ${resp.status}` };
    } catch (err) {
      if (err instanceof Error && err.message.startsWith('Endpoint ')) {
        return { ok: false, message: err.message };
      }
      return { ok: false, message: 'Network error while contacting provider' };
    }
  });

  app.get('/general', async () => {
    return { theme: 'system', language: 'en' };
  });

  app.put('/general', async (req) => {
    return req.body;
  });
}
