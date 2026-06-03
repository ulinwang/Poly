import { describe, it, expect } from 'vitest';
import { buildServer } from '../server';

describe('experiments routes', () => {
  it('GET /api/v1/experiments returns list and stats shape', async () => {
    const app = await buildServer();
    const res = await app.inject({ method: 'GET', url: '/api/v1/experiments' });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(Array.isArray(body.experiments)).toBe(true);
    expect(typeof body.total).toBe('number');
  });

  it('POST /api/v1/experiments creates experiment', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/experiments',
      payload: {
        slug: 'test-market',
        n_agents: 10,
        n_ticks: 5,
        persona_set: 'archetype',
      },
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(typeof body.run_id).toBe('string');

    // GET one
    const getRes = await app.inject({ method: 'GET', url: `/api/v1/experiments/${body.run_id}` });
    expect(getRes.statusCode).toBe(200);
    const exp = JSON.parse(getRes.body).experiment;
    expect(exp.slug).toBe('test-market');

    // Cancel
    const cancelRes = await app.inject({
      method: 'POST',
      url: `/api/v1/experiments/${body.run_id}/cancel`,
    });
    expect(cancelRes.statusCode).toBe(200);
    expect(JSON.parse(cancelRes.body).cancelled).toBe(true);
  });

  it('GET /api/v1/experiments/stats returns stats', async () => {
    const app = await buildServer();
    const res = await app.inject({ method: 'GET', url: '/api/v1/experiments/stats' });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(typeof body.total_runs).toBe('number');
    expect(typeof body.running_count).toBe('number');
  });
});
