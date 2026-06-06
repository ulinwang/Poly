import type { FastifyInstance } from 'fastify';
import { getApiSettings, getApiSettingsDecrypted, saveApiSettings } from '../db/settings';
import type { ApiSettings } from '../types';

const PROVIDER_DEFAULTS: Record<string, { base_url: string }> = {
  deepseek: { base_url: 'https://api.deepseek.com/v1' },
  kimi: { base_url: 'https://api.moonshot.cn/v1' },
  openai: { base_url: 'https://api.openai.com/v1' },
};

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
    // Use the supplied key if present; otherwise fall back to the stored
    // (decrypted) key so "Test" works without re-entering the key.
    const apiKey = body.api_key || getApiSettingsDecrypted()?.api_key || '';
    const model = body.model;
    const baseUrl = body.base_url || PROVIDER_DEFAULTS[provider]?.base_url;

    if (!apiKey) {
      return { ok: false, message: 'API key is required' };
    }
    if (!baseUrl) {
      return { ok: false, message: 'Base URL is required for this provider' };
    }
    if (!model) {
      return { ok: false, message: 'Model is required' };
    }

    // Anthropic uses a different API format; skip live test for now
    if (provider === 'anthropic') {
      return { ok: true, message: 'Anthropic provider selected (live test not yet implemented)' };
    }

    try {
      const resp = await fetch(`${baseUrl}/chat/completions`, {
        method: 'POST',
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
      const errText = await resp.text().catch(() => '');
      return { ok: false, message: `HTTP ${resp.status}: ${errText.slice(0, 200)}` };
    } catch (err) {
      return { ok: false, message: `Network error: ${(err as Error).message}` };
    }
  });

  app.get('/general', async () => {
    return { theme: 'system', language: 'en' };
  });

  app.put('/general', async (req) => {
    return req.body;
  });
}
