import { describe, it, expect, beforeEach } from 'vitest';
import { buildServer } from '../server.js';
import { db } from '../db/index.js';
import { getApiKeyDecrypted } from '../db/apikeys.js';

describe('api keys routes', () => {
  beforeEach(() => {
    db.prepare('DELETE FROM api_keys').run();
  });

  it('GET /api/v1/keys returns empty list initially', async () => {
    const app = await buildServer();
    const res = await app.inject({ method: 'GET', url: '/api/v1/keys' });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).keys).toEqual([]);
  });

  it('POST creates a key; list shows masked preview and never plaintext', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/keys',
      payload: {
        name: 'My DeepSeek',
        provider: 'deepseek',
        api_key: 'sk-secret-plaintext-1234',
        model: 'deepseek-v4-flash',
      },
    });
    expect(res.statusCode).toBe(201);
    const body = JSON.parse(res.body);
    expect(typeof body.id).toBe('number');
    expect(body.keys).toHaveLength(1);
    const k = body.keys[0];
    expect(k.name).toBe('My DeepSeek');
    expect(k.provider).toBe('deepseek');
    // Masked preview only — never the full secret.
    expect(k.key_masked).toBe('sk-…1234');
    expect(JSON.stringify(k)).not.toContain('sk-secret-plaintext-1234');
    expect((k as Record<string, unknown>).api_key).toBeUndefined();
    // Base URL defaulted from the provider catalog.
    expect(k.base_url).toBe('https://api.deepseek.com/v1');
  });

  it('stores the key encrypted, not as plaintext', async () => {
    const app = await buildServer();
    await app.inject({
      method: 'POST',
      url: '/api/v1/keys',
      payload: { name: 'k', provider: 'openai', api_key: 'sk-plain-xyz' },
    });
    const row = db
      .prepare('SELECT api_key FROM api_keys ORDER BY id DESC LIMIT 1')
      .get() as { api_key: string };
    expect(row.api_key).not.toContain('sk-plain-xyz');
    expect(row.api_key.length).toBeGreaterThan(0);
  });

  it('getApiKeyDecrypted round-trips the plaintext key', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/keys',
      payload: {
        name: 'k',
        provider: 'kimi',
        api_key: 'sk-roundtrip-abcd',
        base_url: 'https://example.com/v1',
        model: 'kimi-latest',
      },
    });
    const id = JSON.parse(res.body).id as number;
    const dec = getApiKeyDecrypted(id);
    expect(dec).toBeDefined();
    expect(dec?.api_key).toBe('sk-roundtrip-abcd');
    expect(dec?.base_url).toBe('https://example.com/v1');
    expect(dec?.model).toBe('kimi-latest');
    expect(dec?.provider).toBe('kimi');
  });

  it('POST rejects missing fields', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/keys',
      payload: { name: '', provider: 'openai', api_key: 'sk-x' },
    });
    expect(res.statusCode).toBe(400);
  });

  it('DELETE removes a key', async () => {
    const app = await buildServer();
    const createRes = await app.inject({
      method: 'POST',
      url: '/api/v1/keys',
      payload: { name: 'k', provider: 'openai', api_key: 'sk-del' },
    });
    const id = JSON.parse(createRes.body).id as number;
    const delRes = await app.inject({ method: 'DELETE', url: `/api/v1/keys/${id}` });
    expect(delRes.statusCode).toBe(200);
    expect(JSON.parse(delRes.body).deleted).toBe(true);
    expect(JSON.parse(delRes.body).keys).toEqual([]);
    expect(getApiKeyDecrypted(id)).toBeUndefined();
  });

  it('DELETE returns 404 for unknown id', async () => {
    const app = await buildServer();
    const res = await app.inject({ method: 'DELETE', url: '/api/v1/keys/999999' });
    expect(res.statusCode).toBe(404);
  });
});
