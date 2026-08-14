import { describe, it, expect } from 'vitest';
import { buildServer } from '../server.js';

// These routes spawn a Python subprocess (introspect.py / analysis_cli.py).
// Agent introspection is deliberately dependency-light and must work in the
// normal repository environment. Analysis remains fail-open when optional
// data/Python dependencies are unavailable.

describe('agent + analysis routes', () => {
  it('GET /api/v1/agent/info returns tool/template info', async () => {
    const app = await buildServer();
    const res = await app.inject({ method: 'GET', url: '/api/v1/agent/info' });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(Array.isArray(body.tools)).toBe(true);
    expect(body.tools.length).toBeGreaterThan(0);
    expect(typeof body.prompt_templates).toBe('object');
    expect(Array.isArray(body.architecture?.stages)).toBe(true);
    expect(body.architecture.stages.length).toBeGreaterThan(0);
    expect(Array.isArray(body.configuration)).toBe(true);
    expect(body.configuration.length).toBeGreaterThan(0);
  });

  it('GET /api/v1/analysis/:slug returns 200 with an available flag', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'GET',
      url: '/api/v1/analysis/this-market-does-not-exist-xyz',
    });
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(typeof body.available).toBe('boolean');
    if (!body.available) {
      expect(typeof body.message).toBe('string');
    }
  });
});
