import { describe, it, expect, beforeEach, vi } from 'vitest';
import { buildServer } from '../server';
import { db } from '../db';

describe('settings routes', () => {
  beforeEach(() => {
    db.prepare('DELETE FROM api_settings').run();
  });

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

  it('POST /api/v1/settings/test rejects missing api_key', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/settings/test',
      payload: {
        provider: 'deepseek',
        model: 'deepseek-chat',
        api_key: '',
        base_url: '',
        temperature: 0.7,
        max_tokens: 2048,
      },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.ok).toBe(false);
    expect(body.message).toContain('API key');
  });

  it('POST /api/v1/settings/test returns not-implemented for anthropic', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/settings/test',
      payload: {
        provider: 'anthropic',
        model: 'claude-3-5-sonnet',
        api_key: 'sk-test',
        base_url: 'https://api.anthropic.com',
        temperature: 0.7,
        max_tokens: 2048,
      },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.ok).toBe(true);
    expect(body.message).toContain('not yet implemented');
  });

  it('POST /api/v1/settings/test calls LLM endpoint for openai-compatible provider', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(''),
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const app = await buildServer();
    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/settings/test',
      payload: {
        provider: 'deepseek',
        model: 'deepseek-chat',
        api_key: 'sk-test',
        base_url: '',
        temperature: 0.7,
        max_tokens: 2048,
      },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.ok).toBe(true);
    expect(mockFetch).toHaveBeenCalledTimes(1);

    vi.restoreAllMocks();
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
