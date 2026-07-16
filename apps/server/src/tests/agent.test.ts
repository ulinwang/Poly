import { describe, it, expect } from 'vitest';
import { buildServer } from '../server.js';

// These routes spawn a Python subprocess (introspect.py / analysis_cli.py).
// In CI / isolated worktrees the interpreter may be absent, in which case the
// routes degrade gracefully: /agent/info returns a 500 with a message, and
// /analysis/:slug always returns 200 with { available:false }. The tests below
// assert the route is wired up and never crashes the server, accepting either
// the data-present or the gracefully-degraded shape.

describe('agent + analysis routes', () => {
  it('GET /api/v1/agent/info returns tool/template info or a graceful error', async () => {
    const app = await buildServer();
    const res = await app.inject({ method: 'GET', url: '/api/v1/agent/info' });
    expect([200, 500]).toContain(res.statusCode);
    const body = JSON.parse(res.body);
    if (res.statusCode === 200) {
      expect(Array.isArray(body.tools)).toBe(true);
      expect(typeof body.prompt_templates).toBe('object');
    } else {
      expect(typeof body.message).toBe('string');
    }
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
