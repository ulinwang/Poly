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
    expect(body.settings.api_key_set).toBe(false);
    expect(body.settings.api_key).toBeUndefined();
  });

  it('PUT /api/v1/settings/api updates settings and never returns plaintext key', async () => {
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
    // Response must not include the plaintext key, only a boolean flag.
    expect(body.settings.api_key).toBeUndefined();
    expect(body.settings.api_key_set).toBe(true);
  });

  it('PUT without api_key preserves the previously stored key', async () => {
    const app = await buildServer();
    await app.inject({
      method: 'PUT',
      url: '/api/v1/settings/api',
      payload: {
        provider: 'openai',
        model: 'gpt-4o',
        api_key: 'sk-original',
        temperature: 0.5,
        max_tokens: 1024,
      },
    });
    // Update other fields without supplying a key.
    const res = await app.inject({
      method: 'PUT',
      url: '/api/v1/settings/api',
      payload: {
        provider: 'openai',
        model: 'gpt-4o-mini',
        api_key: '',
        temperature: 0.9,
        max_tokens: 2048,
      },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.settings.model).toBe('gpt-4o-mini');
    // Key should still be set even though none was sent in the second request.
    expect(body.settings.api_key_set).toBe(true);
  });

  it('api_key is stored encrypted, not as plaintext', async () => {
    const app = await buildServer();
    await app.inject({
      method: 'PUT',
      url: '/api/v1/settings/api',
      payload: {
        provider: 'openai',
        model: 'gpt-4o',
        api_key: 'sk-secret-plaintext',
        temperature: 0.5,
        max_tokens: 1024,
      },
    });
    const row = db
      .prepare('SELECT api_key FROM api_settings ORDER BY updated_at DESC, id DESC LIMIT 1')
      .get() as { api_key: string };
    expect(row.api_key).not.toBe('sk-secret-plaintext');
    expect(row.api_key).not.toContain('sk-secret-plaintext');
    expect(row.api_key.length).toBeGreaterThan(0);
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
    expect(body.message).toContain('litellm');
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

  it('GET /providers/:id/models returns live models when /models succeeds', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        data: [{ id: 'deepseek-v4-flash' }, { id: 'deepseek-v4-pro' }],
      }),
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const app = await buildServer();
    const res = await app.inject({
      method: 'GET',
      url: '/api/v1/providers/deepseek/models?api_key=sk-test',
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.source).toBe('live');
    expect(body.models).toEqual(['deepseek-v4-flash', 'deepseek-v4-pro']);
    expect(mockFetch).toHaveBeenCalledTimes(1);

    vi.restoreAllMocks();
  });

  it('GET /providers/:id/models falls back to catalog when /models fails', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: vi.fn().mockResolvedValue({}),
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const app = await buildServer();
    const res = await app.inject({
      method: 'GET',
      url: '/api/v1/providers/deepseek/models?api_key=sk-test',
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.source).toBe('catalog');
    // Static catalog models for deepseek.
    expect(body.models).toContain('deepseek-v4-flash');
    expect(body.message).toContain('401');

    vi.restoreAllMocks();
  });

  it('GET /providers/:id/models returns catalog with no-api-key message when no key', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'GET',
      url: '/api/v1/providers/deepseek/models',
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.source).toBe('catalog');
    expect(body.message).toBe('no api key');
  });

  it('GET /providers/:id/models falls back to catalog for litellm-native provider', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'GET',
      url: '/api/v1/providers/anthropic/models?api_key=sk-test',
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.source).toBe('catalog');
    expect(body.models).toContain('anthropic/claude-opus-4-8');
  });
});
