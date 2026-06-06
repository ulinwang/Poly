import type { FastifyInstance } from 'fastify';
import crypto from 'crypto';
import {
  saveExperiment,
  getExperimentsFiltered,
  searchExperiments,
  getExperimentStats,
  getExperiment,
} from '../db/experiments';
import {
  createRunHandle,
  emitEvent,
  spawnRun,
  pauseRun,
  checkpointPathFor,
  eventLogPathFor,
} from '../services/runner';
import type { ExperimentConfig, ExperimentRow } from '../types';
import { getApiSettingsDecrypted } from '../db/settings';
import { getApiKeyDecrypted } from '../db/apikeys';
import fs from 'fs';
import readline from 'readline';

import type { RunHandle } from '../services/runner';

const runs = new Map<string, RunHandle>();

/**
 * Replay a run's full NDJSON event log to an open SSE response, one line at a
 * time so memory stays bounded regardless of history size. `__end__` sentinels
 * are skipped (the caller decides when to emit the SSE `end` event). Returns
 * true if a log file existed and was replayed, false if none was found.
 */
async function replayEventLog(
  runId: string,
  reply: { raw: { write: (chunk: string) => void } },
): Promise<boolean> {
  const logPath = eventLogPathFor(runId);
  if (!fs.existsSync(logPath)) return false;
  const stream = fs.createReadStream(logPath, { encoding: 'utf8' });
  const rl = readline.createInterface({ input: stream, crlfDelay: Infinity });
  for await (const line of rl) {
    if (!line.trim()) continue;
    try {
      const ev = JSON.parse(line) as { kind: string; data: Record<string, unknown> };
      if (ev.kind === '__end__') continue;
      reply.raw.write(`event: ${ev.kind}\ndata: ${JSON.stringify(ev.data)}\n\n`);
    } catch {
      // ignore malformed lines
    }
  }
  return true;
}

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
    seed: row.seed ?? null,
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
          seed: handle.seed,
        },
      };
    }
    reply.status(404);
    return { message: 'Experiment not found' };
  });

  // Build the per-run event handler. Persists final metrics on `__end__`,
  // distinguishing three terminal states: paused (checkpointed, resumable),
  // cancelled, and completed.
  function makeOnEvent(runId: string, handle: RunHandle) {
    return (kind: string, data: Record<string, unknown>) => {
      emitEvent(handle, kind, data);
      if (kind === '__end__') {
        if (handle.paused) {
          // Paused mid-run: keep result_summary/metrics untouched, record
          // the checkpoint and flip status to 'paused' for later resume.
          saveExperiment({
            id: runId,
            status: 'paused',
            checkpoint_path: handle.checkpointPath,
            finished_at: null,
          });
          return;
        }
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
    };
  }

  // Decrypt the key only here, kept in memory and handed to the Python
  // subprocess; never persisted or returned to the client. When `apiKeyId` is
  // given, use that named key (its provider's key/base_url/model); otherwise
  // fall back to the single default api_settings.
  function currentApiSettings(apiKeyId?: number | null) {
    if (apiKeyId != null) {
      const k = getApiKeyDecrypted(apiKeyId);
      if (k && k.api_key) {
        return { api_key: k.api_key, base_url: k.base_url, model: k.model };
      }
      // Selected key vanished (e.g. deleted) — fall through to default.
    }
    const settings = getApiSettingsDecrypted();
    return settings
      ? { api_key: settings.api_key, base_url: settings.base_url, model: settings.model }
      : undefined;
  }

  app.post('', async (req) => {
    const body = req.body as ExperimentConfig;
    const runId = crypto.randomBytes(12).toString('hex').slice(0, 12);
    const seed = Number.isFinite(body.seed as number) ? Number(body.seed) : 0;
    const temperature = Number.isFinite(body.temperature as number)
      ? Number(body.temperature)
      : 0;
    const apiKeyId = Number.isFinite(body.api_key_id as number)
      ? Number(body.api_key_id)
      : null;
    const handle = createRunHandle(
      runId,
      body.slug,
      body.n_agents,
      body.n_ticks,
      body.persona_set,
      seed,
      temperature,
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
      seed,
      api_key_id: apiKeyId,
    });

    spawnRun(handle, makeOnEvent(runId, handle), {
      apiSettings: currentApiSettings(apiKeyId),
      checkpointOut: checkpointPathFor(runId),
    });

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

  // Pause a running experiment: request a checkpoint, then wait (briefly)
  // for the Python side to emit `paused` at the next tick boundary.
  app.post('/:expId/pause', async (req, reply) => {
    const { expId } = req.params as { expId: string };
    const handle = runs.get(expId);
    if (!handle || handle.finished) {
      reply.status(404);
      return { message: 'No running experiment to pause' };
    }
    if (!pauseRun(handle)) {
      reply.status(409);
      return { message: 'Experiment is not pausable' };
    }
    // Wait up to ~30s for the current tick to finish and the checkpoint
    // to land. The pause fires at a tick boundary, so this bounds at one
    // tick's worth of LLM calls.
    const deadline = Date.now() + 30_000;
    while (!handle.paused && !handle.finished && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 200));
    }
    if (handle.paused) {
      return { paused: true, checkpoint_path: handle.checkpointPath };
    }
    // Timed out or the run ended for another reason.
    reply.status(202);
    return { paused: false, message: 'Pause requested; checkpoint pending' };
  });

  // Resume a paused experiment from its stored checkpoint.
  app.post('/:expId/resume', async (req, reply) => {
    const { expId } = req.params as { expId: string };
    const row = getExperiment(expId);
    if (!row) {
      reply.status(404);
      return { message: 'Experiment not found' };
    }
    if (row.status !== 'paused' || !row.checkpoint_path) {
      reply.status(409);
      return { message: 'Experiment is not paused / has no checkpoint' };
    }

    // Reuse the same expId so the client keeps observing one run; build a
    // fresh RunHandle (the prior one's child has exited).
    const handle = createRunHandle(
      expId,
      row.slug,
      row.n_agents,
      row.n_ticks,
      row.persona_set,
      row.seed ?? 0,
    );
    runs.set(expId, handle);

    saveExperiment({
      id: expId,
      status: 'running',
      finished_at: null,
    });

    spawnRun(handle, makeOnEvent(expId, handle), {
      // Reuse the same named key the run was started with (if any).
      apiSettings: currentApiSettings(row.api_key_id),
      resumeCheckpoint: row.checkpoint_path,
      checkpointOut: checkpointPathFor(expId),
    });

    return { run_id: expId, resumed: true };
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

      // Snapshot the queue length now: everything currently queued is also in
      // the NDJSON log (or in-memory history fallback), so after replay we
      // resume live streaming from this index to avoid duplicates.
      let idx = handle.queue.length;
      if (wantReplay) {
        const replayed = await replayEventLog(expId, reply);
        if (!replayed) {
          // No NDJSON file (e.g. legacy run) — fall back to capped in-memory
          // history.
          for (const ev of handle.history) {
            if (ev.kind === '__end__') continue;
            reply.raw.write(`event: ${ev.kind}\ndata: ${JSON.stringify(ev.data)}\n\n`);
          }
        }
      }

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

    // Fallback: no live handle in memory (e.g. after a restart). Prefer the
    // durable NDJSON log so the full event history is replayed; otherwise fall
    // back to the stored settled summary.
    const row = getExperiment(expId);
    const hasLog = fs.existsSync(eventLogPathFor(expId));
    if (hasLog && wantReplay) {
      reply.raw.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      });
      await replayEventLog(expId, reply);
      reply.raw.write(`event: end\ndata: {}\n\n`);
      reply.raw.end();
      return reply;
    }
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
