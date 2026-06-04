import type { FastifyInstance } from 'fastify';
import crypto from 'crypto';
import {
  saveExperiment,
  getExperimentsFiltered,
  searchExperiments,
  getExperimentStats,
  getExperiment,
} from '../db/experiments';
import { createRunHandle, emitEvent, spawnRun } from '../services/runner';
import type { ExperimentConfig, ExperimentRow } from '../types';
import { getApiSettings } from '../db/settings';

import type { RunHandle } from '../services/runner';

const runs = new Map<string, RunHandle>();

function rowToExperiment(row: ExperimentRow): Record<string, unknown> {
  return {
    id: row.id,
    slug: row.slug,
    n_agents: row.n_agents,
    n_ticks: row.n_ticks,
    persona_set: row.persona_set,
    status: row.status,
    started_at: row.started_at,
    finished_at: row.finished_at,
    elapsed_s: row.started_at
      ? Math.round(Date.now() / 1000 - new Date(row.started_at).getTime() / 1000)
      : 0,
    result_summary: row.result_summary ? JSON.parse(row.result_summary) : null,
  };
}

export default async function experimentsRoutes(app: FastifyInstance) {
  app.get('', async (req) => {
    const { status, slug, limit = '20', offset = '0' } = req.query as Record<string, string>;
    const { rows, total } = getExperimentsFiltered(
      status || undefined,
      slug || undefined,
      parseInt(limit, 10) || 20,
      parseInt(offset, 10) || 0,
    );
    return {
      experiments: rows.map(rowToExperiment),
      total,
      limit: parseInt(limit, 10) || 20,
      offset: parseInt(offset, 10) || 0,
    };
  });

  app.get('/search', async (req) => {
    const { q = '', limit = '20' } = req.query as Record<string, string>;
    if (!q) return { experiments: [] };
    const rows = searchExperiments(q, parseInt(limit, 10) || 20);
    return { experiments: rows.map(rowToExperiment) };
  });

  app.get('/stats', async () => {
    return getExperimentStats();
  });

  app.get('/:expId', async (req, reply) => {
    const { expId } = req.params as { expId: string };
    const row = getExperiment(expId);
    if (row) {
      return { experiment: rowToExperiment(row) };
    }
    const handle = runs.get(expId);
    if (handle) {
      return {
        experiment: {
          id: handle.runId,
          slug: handle.slug,
          n_agents: handle.nAgents,
          n_ticks: handle.nTicks,
          persona_set: handle.personaSet,
          status: handle.finished ? 'completed' : 'running',
          started_at: new Date(handle.startedAt * 1000).toISOString(),
          finished_at: handle.finished ? new Date().toISOString() : null,
          elapsed_s: Math.round(Date.now() / 1000 - handle.startedAt),
          result_summary: null,
        },
      };
    }
    reply.status(404);
    return { message: 'Experiment not found' };
  });

  app.post('', async (req) => {
    const body = req.body as ExperimentConfig;
    const runId = crypto.randomBytes(12).toString('hex').slice(0, 12);
    const handle = createRunHandle(
      runId,
      body.slug,
      body.n_agents,
      body.n_ticks,
      body.persona_set,
    );
    runs.set(runId, handle);

    saveExperiment({
      id: runId,
      slug: body.slug,
      n_agents: body.n_agents,
      n_ticks: body.n_ticks,
      persona_set: body.persona_set,
      status: 'running',
      started_at: new Date().toISOString(),
      finished_at: null,
      result_summary: null,
    });

    const settings = getApiSettings();
    const apiSettings = settings
      ? { api_key: settings.api_key, base_url: settings.base_url, model: settings.model }
      : undefined;

    spawnRun(
      handle,
      (kind: string, data: Record<string, unknown>) => {
        emitEvent(handle, kind, data);
        if (kind === '__end__') {
          const metrics = handle.finalMetrics;
          const payload: Partial<ExperimentRow> = {
            id: runId,
            finished_at: new Date().toISOString(),
            result_summary: metrics ? JSON.stringify(metrics) : null,
            final_yes_mid: metrics.yes_mid_final as number | undefined,
            total_fills: metrics.n_fills as number | undefined,
            total_actions: metrics.n_actions as number | undefined,
            avg_tick_time_ms: handle.tickCount
              ? parseFloat(((handle.tickElapsedTotal / handle.tickCount) * 1000).toFixed(2))
              : undefined,
          };
          if (!handle.cancel) {
            payload.status = 'completed';
          }
          saveExperiment(payload);
        }
      },
      apiSettings,
    );

    return { run_id: runId };
  });

  app.post('/:expId/cancel', async (req, reply) => {
    const { expId } = req.params as { expId: string };
    const handle = runs.get(expId);
    if (!handle) {
      reply.status(404);
      return { message: 'Experiment not found' };
    }
    handle.cancel = true;
    saveExperiment({
      id: expId,
      status: 'cancelled',
      finished_at: new Date().toISOString(),
    });
    return { cancelled: true };
  });

  app.get('/:expId/events', async (req, reply) => {
    const { expId } = req.params as { expId: string };
    const { replay = '1' } = req.query as Record<string, string>;
    const wantReplay = replay !== '0' && replay !== 'false';

    const handle = runs.get(expId);
    if (handle) {
      // Live or recently finished run — stream from in-memory queue
      reply.raw.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      });

      if (wantReplay) {
        for (const ev of handle.history) {
          if (ev.kind === '__end__') continue;
          reply.raw.write(`event: ${ev.kind}\ndata: ${JSON.stringify(ev.data)}\n\n`);
        }
      }

      let idx = handle.history.length;
      const timer = setInterval(() => {
        while (idx < handle.queue.length) {
          const ev = handle.queue[idx++];
          if (ev.kind === '__end__') {
            reply.raw.write(`event: end\ndata: {}\n\n`);
            clearInterval(timer);
            reply.raw.end();
            return;
          }
          reply.raw.write(`event: ${ev.kind}\ndata: ${JSON.stringify(ev.data)}\n\n`);
        }
        if (handle.finished && idx >= handle.queue.length) {
          reply.raw.write(`event: end\ndata: {}\n\n`);
          clearInterval(timer);
          reply.raw.end();
          return;
        }
        reply.raw.write(`event: ping\ndata: {}\n\n`);
      }, 250);

      req.raw.on('close', () => {
        clearInterval(timer);
      });

      return reply;
    }

    // Fallback: check SQLite for completed experiments
    const row = getExperiment(expId);
    if (row && row.result_summary) {
      reply.raw.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      });
      try {
        const summary = JSON.parse(row.result_summary);
        reply.raw.write(`event: settled\ndata: ${JSON.stringify(summary)}\n\n`);
      } catch {
        reply.raw.write(`event: settled\ndata: {}\n\n`);
      }
      reply.raw.write(`event: end\ndata: {}\n\n`);
      reply.raw.end();
      return reply;
    }

    reply.status(404);
    return { message: 'Experiment not found' };
  });
}
