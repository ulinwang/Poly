import { lookup } from 'node:dns/promises';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { buildServer } from '../server.js';
import { db } from '../db/index.js';

vi.mock('node:dns/promises', () => ({
  lookup: vi.fn(),
}));

const originalFetch = global.fetch;

describe('settings routes', () => {
  beforeEach(() => {
    db.prepare('DELETE FROM api_settings').run();
    vi.clearAllMocks();
    vi.mocked(lookup).mockResolvedValue([
      { address: '93.184.216.34', family: 4 },
    ] as never);
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.unstubAllEnvs();
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

  it('PUT without a new key clears the key when the endpoint changes', async () => {
    const mockFetch = vi.fn();
    global.fetch = mockFetch as unknown as typeof fetch;
    const app = await buildServer();
    await app.inject({
      method: 'PUT',
      url: '/api/v1/settings/api',
      payload: {
        provider: 'openai',
        model: 'gpt-4o',
        api_key: 'sk-original',
        base_url: 'https://api.openai.com/v1',
        temperature: 0.5,
        max_tokens: 1024,
      },
    });

    const update = await app.inject({
      method: 'PUT',
      url: '/api/v1/settings/api',
      payload: {
        provider: 'openai',
        model: 'gpt-4o',
        api_key: '',
        base_url: 'https://attacker.example/v1',
        temperature: 0.5,
        max_tokens: 1024,
      },
    });
    expect(JSON.parse(update.body).settings.api_key_set).toBe(false);

    const test = await app.inject({
      method: 'POST',
      url: '/api/v1/settings/test',
      payload: {
        provider: 'openai',
        model: 'gpt-4o',
        api_key: '',
        base_url: 'https://attacker.example/v1',
      },
    });
    expect(JSON.parse(test.body)).toEqual({
      ok: false,
      message: 'API key is required',
    });
    expect(mockFetch).not.toHaveBeenCalled();
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
    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.deepseek.com/v1/chat/completions',
      expect.objectContaining({
        redirect: 'error',
        signal: expect.any(AbortSignal),
        headers: expect.objectContaining({ Authorization: 'Bearer sk-test' }),
      }),
    );
  });

  it('does not send a stored key to a request-supplied endpoint', async () => {
    const mockFetch = vi.fn();
    global.fetch = mockFetch as unknown as typeof fetch;
    const app = await buildServer();
    await app.inject({
      method: 'PUT',
      url: '/api/v1/settings/api',
      payload: {
        provider: 'openai',
        model: 'gpt-4o',
        api_key: 'sk-stored-secret',
        base_url: 'https://api.openai.com/v1',
        temperature: 0.5,
        max_tokens: 1024,
      },
    });

    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/settings/test',
      payload: {
        provider: 'openai',
        model: 'gpt-4o',
        api_key: '',
        base_url: 'https://attacker.example/v1',
      },
    });

    expect(JSON.parse(res.body)).toEqual({
      ok: false,
      message: 'Enter an API key before testing a different provider or endpoint',
    });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('allows a stored key only for its saved provider and endpoint', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    global.fetch = mockFetch as unknown as typeof fetch;
    const app = await buildServer();
    await app.inject({
      method: 'PUT',
      url: '/api/v1/settings/api',
      payload: {
        provider: 'openai',
        model: 'gpt-4o',
        api_key: 'sk-stored-secret',
        base_url: 'https://api.openai.com/v1/',
        temperature: 0.5,
        max_tokens: 1024,
      },
    });

    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/settings/test',
      payload: {
        provider: 'openai',
        model: 'gpt-4o-mini',
        api_key: '',
        base_url: 'https://api.openai.com/v1',
      },
    });

    expect(JSON.parse(res.body).ok).toBe(true);
    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.openai.com/v1/chat/completions',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer sk-stored-secret' }),
      }),
    );
  });

  it('rejects private endpoints even when the request supplies a key', async () => {
    const mockFetch = vi.fn();
    global.fetch = mockFetch as unknown as typeof fetch;
    const app = await buildServer();

    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/settings/test',
      payload: {
        provider: 'custom',
        model: 'local-model',
        api_key: 'request-owned-key',
        base_url: 'https://127.0.0.1:11434/v1',
      },
    });

    expect(JSON.parse(res.body)).toEqual({
      ok: false,
      message: 'Endpoint host is not publicly routable',
    });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('rejects hostnames that resolve to a private address', async () => {
    vi.mocked(lookup).mockResolvedValue([
      { address: '10.0.0.8', family: 4 },
    ] as never);
    const mockFetch = vi.fn();
    global.fetch = mockFetch as unknown as typeof fetch;
    const app = await buildServer();

    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/settings/test',
      payload: {
        provider: 'custom',
        model: 'internal-model',
        api_key: 'request-owned-key',
        base_url: 'https://internal.example/v1',
      },
    });

    expect(JSON.parse(res.body)).toEqual({
      ok: false,
      message: 'Endpoint host is not publicly routable',
    });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('rejects credentials embedded in endpoint URLs', async () => {
    const mockFetch = vi.fn();
    global.fetch = mockFetch as unknown as typeof fetch;
    const app = await buildServer();

    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/settings/test',
      payload: {
        provider: 'custom',
        model: 'custom-model',
        api_key: 'request-owned-key',
        base_url: 'https://user:password@example.com/v1',
      },
    });

    expect(JSON.parse(res.body)).toEqual({
      ok: false,
      message: 'Endpoint URL must not include credentials',
    });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('permits an exact operator-allowlisted private origin', async () => {
    vi.stubEnv('POLY_LLM_ENDPOINT_ALLOWLIST', 'http://127.0.0.1:11434');
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    global.fetch = mockFetch as unknown as typeof fetch;
    const app = await buildServer();

    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/settings/test',
      payload: {
        provider: 'custom',
        model: 'local-model',
        api_key: 'request-owned-key',
        base_url: 'http://127.0.0.1:11434/v1',
      },
    });

    expect(JSON.parse(res.body).ok).toBe(true);
    expect(mockFetch).toHaveBeenCalledWith(
      'http://127.0.0.1:11434/v1/chat/completions',
      expect.objectContaining({ redirect: 'error' }),
    );
  });

  it('does not expose an upstream response body', async () => {
    const responseText = vi.fn().mockResolvedValue('sensitive upstream details');
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: responseText,
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
      },
    });

    expect(JSON.parse(res.body)).toEqual({
      ok: false,
      message: 'Provider returned HTTP 401',
    });
    expect(responseText).not.toHaveBeenCalled();
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
