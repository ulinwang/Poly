import { describe, expect, it } from 'vitest';
import { buildServer } from '../server.js';

const OPERATOR_TOKEN = 'operator-token-that-is-at-least-32-characters';
const READER_TOKEN = 'reader-token-that-is-also-at-least-32-characters';

function authorization(token: string) {
  return { authorization: `Bearer ${token}` };
}

describe('API authentication', () => {
  it('keeps explicitly classified public routes anonymous', async () => {
    const app = await buildServer({
      authRequired: true,
      operatorToken: OPERATOR_TOKEN,
    });

    const config = await app.inject({ method: 'GET', url: '/api/v1/auth/config' });
    expect(config.statusCode).toBe(200);
    expect(JSON.parse(config.body)).toEqual({ required: true, mode: 'bearer' });

    const providers = await app.inject({ method: 'GET', url: '/api/v1/providers' });
    expect(providers.statusCode).toBe(200);
  });

  it.each([
    '/api/v1/settings/api',
    '/api/v1/keys',
    '/api/v1/experiments',
    '/api/v1/experiments/example/replay',
    '/api/v1/experiments/example/events',
    '/api/v1/providers/deepseek/models',
    '/api/v1/agent/info',
    '/api/v1/analysis/example',
  ])('returns 401 for anonymous access to %s', async (url) => {
    const app = await buildServer({
      authRequired: true,
      operatorToken: OPERATOR_TOKEN,
    });
    const res = await app.inject({ method: 'GET', url });

    expect(res.statusCode).toBe(401);
    expect(res.headers['www-authenticate']).toBe('Bearer realm="Poly"');
    expect(JSON.parse(res.body).message).toBe('Authentication required');
  });

  it('returns 401 for invalid or malformed credentials', async () => {
    const app = await buildServer({
      authRequired: true,
      operatorToken: OPERATOR_TOKEN,
    });

    const invalid = await app.inject({
      method: 'GET',
      url: '/api/v1/experiments',
      headers: authorization('wrong-token-that-is-at-least-32-characters'),
    });
    const malformed = await app.inject({
      method: 'GET',
      url: '/api/v1/experiments',
      headers: { authorization: `Basic ${OPERATOR_TOKEN}` },
    });

    expect(invalid.statusCode).toBe(401);
    expect(malformed.statusCode).toBe(401);
  });

  it('accepts the operator token for reads and mutations', async () => {
    const app = await buildServer({
      authRequired: true,
      operatorToken: OPERATOR_TOKEN,
    });

    const verify = await app.inject({
      method: 'GET',
      url: '/api/v1/auth/verify',
      headers: authorization(OPERATOR_TOKEN),
    });
    const update = await app.inject({
      method: 'PUT',
      url: '/api/v1/settings/general',
      headers: authorization(OPERATOR_TOKEN),
      payload: { theme: 'dark' },
    });

    expect(verify.statusCode).toBe(200);
    expect(JSON.parse(verify.body).role).toBe('operator');
    expect(update.statusCode).toBe(200);
  });

  it('allows a reader token to read but returns 403 for mutations', async () => {
    const app = await buildServer({
      authRequired: true,
      operatorToken: OPERATOR_TOKEN,
      readerToken: READER_TOKEN,
    });

    const read = await app.inject({
      method: 'GET',
      url: '/api/v1/experiments',
      headers: authorization(READER_TOKEN),
    });
    const write = await app.inject({
      method: 'PUT',
      url: '/api/v1/settings/general',
      headers: authorization(READER_TOKEN),
      payload: { theme: 'dark' },
    });

    expect(read.statusCode).toBe(200);
    expect(write.statusCode).toBe(403);
    expect(JSON.parse(write.body).message).toBe('Operator permission required');
  });

  it('never accepts credentials from a query string', async () => {
    const app = await buildServer({
      authRequired: true,
      operatorToken: OPERATOR_TOKEN,
    });
    const res = await app.inject({
      method: 'GET',
      url: `/api/v1/experiments?access_token=${OPERATOR_TOKEN}`,
    });

    expect(res.statusCode).toBe(401);
  });

  it('fails closed when authentication is required without a strong operator token', async () => {
    await expect(buildServer({ authRequired: true })).rejects.toThrow('POLY_API_TOKEN');
    await expect(
      buildServer({ authRequired: true, operatorToken: 'too-short' }),
    ).rejects.toThrow('at least 32 characters');
  });
});
