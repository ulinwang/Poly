import { describe, expect, it } from 'vitest';
import { buildServer, LOG_REDACT_PATHS } from '../server.js';

const OPERATOR_TOKEN = 'operator-token-that-is-at-least-32-characters';

describe('service health and logging safety', () => {
  it('keeps liveness and readiness public without exposing internals', async () => {
    const app = await buildServer({
      authRequired: true,
      operatorToken: OPERATOR_TOKEN,
    });

    const live = await app.inject({ method: 'GET', url: '/api/v1/health/live' });
    const ready = await app.inject({ method: 'GET', url: '/api/v1/health/ready' });

    expect(live.statusCode).toBe(200);
    expect(JSON.parse(live.body)).toEqual({ status: 'ok' });
    expect(ready.statusCode).toBe(200);
    expect(JSON.parse(ready.body)).toEqual({ status: 'ready' });
    expect(live.headers['x-request-id']).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
    expect(Object.keys(JSON.parse(ready.body))).toEqual(['status']);
    await app.close();
  });

  it('redacts credentials from structured log objects', () => {
    expect(LOG_REDACT_PATHS).toEqual(
      expect.arrayContaining([
        'req.headers.authorization',
        'req.headers.cookie',
        'req.body.api_key',
        'apiSettings.api_key',
      ]),
    );
  });
});
