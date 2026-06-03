import { describe, it, expect } from 'vitest';
import { buildServer } from '../server';

async function makeApp() {
  const app = await buildServer();
  return app;
}

describe('markets routes', () => {
  it('GET /api/v1/markets returns markets list', async () => {
    const app = await makeApp();
    const res = await app.inject({ method: 'GET', url: '/api/v1/markets' });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(Array.isArray(body.markets)).toBe(true);
  });

  it('GET /api/v1/markets?q=bitcoin returns filtered list', async () => {
    const app = await makeApp();
    const res = await app.inject({ method: 'GET', url: '/api/v1/markets?q=bitcoin' });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(Array.isArray(body.markets)).toBe(true);
  });

  it('GET /api/v1/markets/categories returns categories', async () => {
    const app = await makeApp();
    const res = await app.inject({ method: 'GET', url: '/api/v1/markets/categories' });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(Array.isArray(body.categories)).toBe(true);
    expect(body.categories.length).toBeGreaterThan(0);
  });

  it('GET /api/v1/markets/:slug returns market or 404', async () => {
    const app = await makeApp();
    const res = await app.inject({ method: 'GET', url: '/api/v1/markets/nonexistent' });
    expect(res.statusCode).toBe(404);
  });
});
