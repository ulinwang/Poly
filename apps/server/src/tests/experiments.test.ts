import { describe, it, expect, vi } from 'vitest';
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { buildServer } from '../server.js';
import { eventLogPathFor } from '../services/runner.js';
import {
  saveExperiment,
  getExperiment,
  getExperimentsFiltered,
  repairOrphanedRuns,
} from '../db/experiments.js';

describe('experiments routes', () => {
  const validExperiment = {
    slug: 'market',
    n_agents: 2,
    n_ticks: 3,
    persona_set: 'archetype',
  };

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

  it('persists seed on POST and surfaces it on GET', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/experiments',
      payload: {
        slug: 'seed-market',
        n_agents: 5,
        n_ticks: 3,
        persona_set: 'archetype',
        seed: 1234,
      },
    });
    expect(res.statusCode).toBe(200);
    const runId = JSON.parse(res.body).run_id as string;

    const getRes = await app.inject({ method: 'GET', url: `/api/v1/experiments/${runId}` });
    const exp = JSON.parse(getRes.body).experiment;
    expect(exp.seed).toBe(1234);

    await app.inject({ method: 'POST', url: `/api/v1/experiments/${runId}/cancel` });
  });

  it('persists api_key_id chosen for a run', async () => {
    const app = await buildServer();
    // Create a named key to reference.
    const keyRes = await app.inject({
      method: 'POST',
      url: '/api/v1/keys',
      payload: { name: 'exp-key', provider: 'openai', api_key: 'sk-exp' },
    });
    const keyId = JSON.parse(keyRes.body).id as number;

    const res = await app.inject({
      method: 'POST',
      url: '/api/v1/experiments',
      payload: {
        slug: 'keyed-market',
        n_agents: 4,
        n_ticks: 2,
        persona_set: 'archetype',
        api_key_id: keyId,
      },
    });
    expect(res.statusCode).toBe(200);
    const runId = JSON.parse(res.body).run_id as string;
    expect(getExperiment(runId)?.api_key_id).toBe(keyId);

    await app.inject({ method: 'POST', url: `/api/v1/experiments/${runId}/cancel` });
  });

  it('rejects malformed and oversized create requests before saving or spawning', async () => {
    const spawnExperiment = vi.fn();
    const app = await buildServer({
      experimentLimits: {
        maxAgents: 2,
        maxTicks: 5,
        maxSlugLength: 10,
        maxSeed: 100,
        minTemperature: 0,
        maxTemperature: 1,
      },
      spawnExperiment,
    });
    const totalBefore = getExperimentsFiltered(undefined, undefined, 1, 0).total;
    const invalidPayloads: Array<Record<string, unknown>> = [
      { ...validExperiment, slug: undefined },
      { ...validExperiment, n_agents: '2' },
      { ...validExperiment, n_ticks: -1 },
      { ...validExperiment, n_agents: 3 },
      { ...validExperiment, n_ticks: 6 },
      { ...validExperiment, slug: '           ' },
      { ...validExperiment, slug: 'market-name-too-long' },
      { ...validExperiment, persona_set: 'unknown' },
      { ...validExperiment, seed: -1 },
      { ...validExperiment, seed: 101 },
      { ...validExperiment, temperature: 1.1 },
      { ...validExperiment, api_key_id: '1' },
      { ...validExperiment, unexpected: true },
    ];

    for (const payload of invalidPayloads) {
      const response = await app.inject({
        method: 'POST',
        url: '/api/v1/experiments',
        payload,
      });
      expect(response.statusCode, JSON.stringify(payload)).toBe(400);
    }

    const nonFiniteResponse = await app.inject({
      method: 'POST',
      url: '/api/v1/experiments',
      headers: { 'content-type': 'application/json' },
      payload:
        '{"slug":"market","n_agents":2,"n_ticks":3,"persona_set":"archetype","temperature":1e400}',
    });
    expect(nonFiniteResponse.statusCode).toBe(400);
    expect(getExperimentsFiltered(undefined, undefined, 1, 0).total).toBe(totalBefore);
    expect(spawnExperiment).not.toHaveBeenCalled();
    await app.close();
  });

  it('rejects an unknown API key without falling back to default settings', async () => {
    const spawnExperiment = vi.fn();
    const app = await buildServer({ spawnExperiment });
    const totalBefore = getExperimentsFiltered(undefined, undefined, 1, 0).total;

    const response = await app.inject({
      method: 'POST',
      url: '/api/v1/experiments',
      payload: { ...validExperiment, api_key_id: 2_147_483_647 },
    });

    expect(response.statusCode).toBe(400);
    expect(JSON.parse(response.body).message).toContain('usable key');
    expect(getExperimentsFiltered(undefined, undefined, 1, 0).total).toBe(totalBefore);
    expect(spawnExperiment).not.toHaveBeenCalled();
    await app.close();
  });

  it('exposes effective limits and rejects a concurrent run above capacity', async () => {
    const spawnExperiment = vi.fn();
    const app = await buildServer({
      experimentLimits: { maxAgents: 8, maxTicks: 12, maxActiveRuns: 1 },
      spawnExperiment,
    });
    const totalBefore = getExperimentsFiltered(undefined, undefined, 1, 0).total;

    const limitsResponse = await app.inject({
      method: 'GET',
      url: '/api/v1/experiments/limits',
    });
    expect(limitsResponse.statusCode).toBe(200);
    expect(JSON.parse(limitsResponse.body)).toMatchObject({
      max_agents: 8,
      max_ticks: 12,
      max_active_runs: 1,
    });

    const first = await app.inject({
      method: 'POST',
      url: '/api/v1/experiments',
      payload: validExperiment,
    });
    const second = await app.inject({
      method: 'POST',
      url: '/api/v1/experiments',
      payload: { ...validExperiment, slug: 'second-market' },
    });

    expect(first.statusCode).toBe(200);
    expect(second.statusCode).toBe(429);
    expect(second.headers['retry-after']).toBe('5');
    expect(getExperimentsFiltered(undefined, undefined, 1, 0).total).toBe(totalBefore + 1);
    expect(spawnExperiment).toHaveBeenCalledTimes(1);
    await app.close();
  });

  it('validates list and search query parameters', async () => {
    const app = await buildServer({ spawnExperiment: vi.fn() });
    const invalidUrls = [
      '/api/v1/experiments?limit=0',
      '/api/v1/experiments?limit=1001',
      '/api/v1/experiments?offset=-1',
      '/api/v1/experiments?status=unknown',
      '/api/v1/experiments?unexpected=true',
      '/api/v1/experiments/search',
      '/api/v1/experiments/search?q=',
      '/api/v1/experiments/search?q=market&limit=1001',
    ];

    for (const url of invalidUrls) {
      const response = await app.inject({ method: 'GET', url });
      expect(response.statusCode, url).toBe(400);
    }

    const validList = await app.inject({
      method: 'GET',
      url: '/api/v1/experiments?limit=2&offset=0&status=running',
    });
    const validSearch = await app.inject({
      method: 'GET',
      url: '/api/v1/experiments/search?q=market&limit=2',
    });
    expect(validList.statusCode).toBe(200);
    expect(validSearch.statusCode).toBe(200);
    await app.close();
  });

  it('GET /:id/replay returns bounded cursor pages (skips __end__)', async () => {
    const app = await buildServer();
    const runId = 'replaytest' + crypto.randomBytes(4).toString('hex');
    const logPath = eventLogPathFor(runId);
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    const lines = [
      { kind: 'run_started', data: { slug: 'replay-market' } },
      { kind: 'tick_started', data: { tick: 0 } },
      { kind: 'tick_metrics', data: { tick: 0, yes_mid: 0.51 } },
      { kind: '__end__', data: {} },
    ];
    fs.writeFileSync(logPath, lines.map((l) => JSON.stringify(l)).join('\n') + '\n');

    try {
      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/experiments/${runId}/replay?cursor=0&limit=2`,
      });
      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.total).toBe(2);
      expect(Array.isArray(body.events)).toBe(true);
      expect(body.events[0].kind).toBe('run_started');
      expect(body.next_cursor).toBe(2);
      expect(body.events.some((e: { kind: string }) => e.kind === '__end__')).toBe(false);

      const next = await app.inject({
        method: 'GET',
        url: `/api/v1/experiments/${runId}/replay?cursor=${body.next_cursor}&limit=2`,
      });
      const nextBody = JSON.parse(next.body);
      expect(nextBody.events).toHaveLength(1);
      expect(nextBody.events[0].data.yes_mid).toBe(0.51);
      expect(nextBody.next_cursor).toBeNull();
    } finally {
      fs.rmSync(logPath, { force: true });
    }
  });

  it('GET /:id/replay returns 404 when no event log exists', async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: 'GET',
      url: `/api/v1/experiments/nolog${crypto.randomBytes(4).toString('hex')}/replay`,
    });
    expect(res.statusCode).toBe(404);
  });

  it('GET /:id/replay rejects invalid or oversized page parameters', async () => {
    const app = await buildServer();
    for (const query of ['cursor=-1', 'limit=0', 'limit=5001']) {
      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/experiments/example/replay?${query}`,
      });
      expect(res.statusCode, query).toBe(400);
    }
    await app.close();
  });

  it('repairOrphanedRuns flips running -> error but leaves paused alone', () => {
    const runningId = crypto.randomBytes(8).toString('hex');
    const pausedId = crypto.randomBytes(8).toString('hex');
    saveExperiment({
      id: runningId,
      slug: 'orphan',
      n_agents: 3,
      n_ticks: 2,
      persona_set: 'archetype',
      status: 'running',
      started_at: new Date().toISOString(),
    });
    saveExperiment({
      id: pausedId,
      slug: 'orphan',
      n_agents: 3,
      n_ticks: 2,
      persona_set: 'archetype',
      status: 'paused',
      checkpoint_path: '/tmp/x.pkl',
      started_at: new Date().toISOString(),
    });

    repairOrphanedRuns();

    expect(getExperiment(runningId)?.status).toBe('error');
    expect(getExperiment(pausedId)?.status).toBe('paused');
  });
});
