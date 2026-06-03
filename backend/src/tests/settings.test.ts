import { describe, it, expect } from 'vitest';
import { buildServer } from '../server';

describe('settings routes', () => {
  it('GET /api/v1/settings/api returns defaults when empty', async () => {
    const app = await buildServer();
    const res = await app.inject({ method: 'GET', url: '/api/v1/settings/api' });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.settings).toBeDefined();
    expect(body.settings.provider).toBe('deepseek');
  });

  it('PUT /api/v1/settings/api updates settings', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'PUT',
      url: '/api/v1/settings/api',
      payload: {
        provider: 'openai',
        model: 'gpt-4o',
        api_key: 'sk-test',
        temperature: 0.5,
        max_tokens: 1024,
      },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.settings.provider).toBe('openai');
  });

  it('GET /api/v1/settings/general returns placeholder', async () => {
    const app = await buildServer();
    const res = await app.inject({ method: 'GET', url: '/api/v1/settings/general' });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).theme).toBe('system');
  });

  it('GET /api/v1/providers returns providers', async () => {
    const app = await buildServer();
    const res = await app.inject({ method: 'GET', url: '/api/v1/providers' });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(Array.isArray(body.providers)).toBe(true);
    expect(body.providers.length).toBeGreaterThan(0);
  });
});
