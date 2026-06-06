import { describe, it, expect } from 'vitest';
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { buildServer } from '../server';
import { eventLogPathFor } from '../services/runner';
import {
  saveExperiment,
  getExperiment,
  repairOrphanedRuns,
} from '../db/experiments';

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

  it('GET /:id/replay returns the recorded events array (skips __end__)', async () => {
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
      const res = await app.inject({ method: 'GET', url: `/api/v1/experiments/${runId}/replay` });
      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.total).toBe(3); // __end__ filtered out
      expect(Array.isArray(body.events)).toBe(true);
      expect(body.events[0].kind).toBe('run_started');
      expect(body.events[2].data.yes_mid).toBe(0.51);
      expect(body.events.some((e: { kind: string }) => e.kind === '__end__')).toBe(false);
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
