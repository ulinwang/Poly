import type { FastifyInstance } from 'fastify';
import { getApiSettings, saveApiSettings } from '../db/settings';
import type { ApiSettings } from '../types';

export default async function settingsRoutes(app: FastifyInstance) {
  app.get('/api', async () => {
    const row = getApiSettings();
    if (!row) {
      const defaults: ApiSettings = {
        provider: 'deepseek',
        model: 'deepseek-chat',
        api_key: '',
        base_url: undefined,
        temperature: 0.7,
        max_tokens: 2048,
      };
      return { settings: defaults };
    }
    return { settings: row };
  });

  app.put('/api', async (req) => {
    const body = req.body as ApiSettings;
    const payload: Omit<ApiSettings, 'id'> & { id?: number } = {
      provider: body.provider,
      model: body.model,
      api_key: body.api_key,
      base_url: body.base_url,
      temperature: body.temperature,
      max_tokens: body.max_tokens,
    };
    saveApiSettings(payload);
    return { settings: body };
  });

  app.get('/general', async () => {
    return { theme: 'system', language: 'en' };
  });

  app.put('/general', async (req) => {
    return req.body;
  });
}
