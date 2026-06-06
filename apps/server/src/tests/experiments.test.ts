import { describe, it, expect } from 'vitest';
import crypto from 'crypto';
import { buildServer } from '../server';
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
