import type {
  FastifyInstance,
  FastifyPluginOptions,
  FastifyReply,
} from 'fastify';
import crypto from 'crypto';
import {
  saveExperiment,
  getExperimentsFiltered,
  searchExperiments,
  getExperimentStats,
  getExperiment,
} from '../db/experiments.js';
import {
  createRunHandle,
  emitEvent,
  spawnRun as spawnRunDefault,
  pauseRun,
  checkpointPathFor,
  eventLogPathFor,
  flushEventLog,
  eventLogState,
  shutdownRun,
} from '../services/runner.js';
import type { ExperimentConfig, ExperimentRow } from '../types/index.js';
import { getApiSettingsDecrypted } from '../db/settings.js';
import { getApiKeyDecrypted } from '../db/apikeys.js';
import fs from 'fs';
import readline from 'readline';
import { config } from '../config.js';
import { sseFrame, writeSseChunk } from '../services/sse.js';

import type { RunHandle, SpawnOptions } from '../services/runner.js';

const PERSONA_SETS = ['archetype', 'calibrated', 'no_signal'] as const;
const EXPERIMENT_STATUSES = [
  'queued',
  'running',
  'paused',
  'completed',
  'cancelled',
  'error',
] as const;
const CREATE_BODY_KEYS = new Set([
  'slug',
  'n_agents',
  'n_ticks',
  'persona_set',
  'api_key_id',
  'seed',
  'temperature',
]);

export interface ExperimentLimits {
  maxAgents: number;
  maxTicks: number;
  maxActiveRuns: number;
  maxSlugLength: number;
  maxSeed: number;
  minTemperature: number;
  maxTemperature: number;
  maxPageSize: number;
}

interface ExperimentsRouteOptions extends FastifyPluginOptions {
  limits?: Partial<ExperimentLimits>;
  spawnRun?: (
    handle: RunHandle,
    onEvent: (kind: string, data: Record<string, unknown>) => void,
    options?: SpawnOptions,
  ) => void;
}

const DEFAULT_LIMITS: ExperimentLimits = {
  maxAgents: config.MAX_EXPERIMENT_AGENTS,
  maxTicks: config.MAX_EXPERIMENT_TICKS,
  maxActiveRuns: config.MAX_ACTIVE_RUNS,
  maxSlugLength: 200,
  maxSeed: 0xffff_ffff,
  minTemperature: 0,
  maxTemperature: 2,
  maxPageSize: 1_000,
};

function validateLimits(limits: ExperimentLimits): void {
  const positiveIntegerLimits = [
    limits.maxAgents,
    limits.maxTicks,
    limits.maxActiveRuns,
    limits.maxSlugLength,
    limits.maxPageSize,
  ];
  if (
    positiveIntegerLimits.some(
      (value) => !Number.isSafeInteger(value) || value < 1,
    )
  ) {
    throw new Error('Experiment count limits must be positive integers');
  }
  if (!Number.isSafeInteger(limits.maxSeed) || limits.maxSeed < 0) {
    throw new Error('Experiment max seed must be a non-negative integer');
  }
  if (
    !Number.isFinite(limits.minTemperature) ||
    !Number.isFinite(limits.maxTemperature) ||
    limits.minTemperature > limits.maxTemperature
  ) {
    throw new Error('Experiment temperature limits are invalid');
  }
}

function createBodyError(value: unknown, limits: ExperimentLimits): string | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return 'Request body must be a JSON object';
  }
  const body = value as Record<string, unknown>;
  const unexpectedKey = Object.keys(body).find((key) => !CREATE_BODY_KEYS.has(key));
  if (unexpectedKey) {
    return `Unknown request field: ${unexpectedKey}`;
  }
  if (typeof body.slug !== 'string' || body.slug.trim().length === 0) {
    return 'slug must be a non-empty string';
  }
  if (body.slug.length > limits.maxSlugLength) {
    return `slug must be at most ${limits.maxSlugLength} characters`;
  }
  if (
    typeof body.n_agents !== 'number' ||
    !Number.isSafeInteger(body.n_agents) ||
    body.n_agents < 1 ||
    body.n_agents > limits.maxAgents
  ) {
    return `n_agents must be an integer between 1 and ${limits.maxAgents}`;
  }
  if (
    typeof body.n_ticks !== 'number' ||
    !Number.isSafeInteger(body.n_ticks) ||
    body.n_ticks < 1 ||
    body.n_ticks > limits.maxTicks
  ) {
    return `n_ticks must be an integer between 1 and ${limits.maxTicks}`;
  }
  if (
    typeof body.persona_set !== 'string' ||
    !PERSONA_SETS.includes(body.persona_set as (typeof PERSONA_SETS)[number])
  ) {
    return `persona_set must be one of: ${PERSONA_SETS.join(', ')}`;
  }
  if (
    body.seed !== undefined &&
    (typeof body.seed !== 'number' ||
      !Number.isSafeInteger(body.seed) ||
      body.seed < 0 ||
      body.seed > limits.maxSeed)
  ) {
    return `seed must be an integer between 0 and ${limits.maxSeed}`;
  }
  if (
    body.temperature !== undefined &&
    (typeof body.temperature !== 'number' ||
      !Number.isFinite(body.temperature) ||
      body.temperature < limits.minTemperature ||
      body.temperature > limits.maxTemperature)
  ) {
    return `temperature must be between ${limits.minTemperature} and ${limits.maxTemperature}`;
  }
  if (
    body.api_key_id !== undefined &&
    (typeof body.api_key_id !== 'number' ||
      !Number.isSafeInteger(body.api_key_id) ||
      body.api_key_id < 1)
  ) {
    return 'api_key_id must be a positive integer';
  }
  return null;
}

function sendBadRequest(reply: FastifyReply, message: string) {
  return reply.status(400).send({ message });
}

function rejectUnknownQueryKeys(
  query: unknown,
  allowedKeys: readonly string[],
  reply: FastifyReply,
) {
  if (!query || typeof query !== 'object' || Array.isArray(query)) return;
  const allowed = new Set(allowedKeys);
  const unexpectedKey = Object.keys(query).find((key) => !allowed.has(key));
  if (unexpectedKey) {
    return sendBadRequest(reply, `Unknown query parameter: ${unexpectedKey}`);
  }
}

function createExperimentSchema(limits: ExperimentLimits) {
  return {
    body: {
      type: 'object',
      additionalProperties: false,
      required: ['slug', 'n_agents', 'n_ticks', 'persona_set'],
      properties: {
        slug: { type: 'string', minLength: 1, maxLength: limits.maxSlugLength },
        n_agents: { type: 'integer', minimum: 1, maximum: limits.maxAgents },
        n_ticks: { type: 'integer', minimum: 1, maximum: limits.maxTicks },
        persona_set: { type: 'string', enum: [...PERSONA_SETS] },
        api_key_id: { type: 'integer', minimum: 1 },
        seed: { type: 'integer', minimum: 0, maximum: limits.maxSeed, default: 0 },
        temperature: {
          type: 'number',
          minimum: limits.minTemperature,
          maximum: limits.maxTemperature,
          default: 0,
        },
      },
    },
  } as const;
}

/**
 * Replay a run's full NDJSON event log to an open SSE response, one line at a
 * time so memory stays bounded regardless of history size. `__end__` sentinels
 * are skipped (the caller decides when to emit the SSE `end` event). Returns
 * true if a log file existed and was replayed, false if none was found.
 */
async function replayEventLog(
  runId: string,
  reply: FastifyReply,
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
      if (!(await writeSseChunk(reply.raw, sseFrame(ev.kind, ev.data)))) {
        rl.close();
        stream.destroy();
        break;
      }
    } catch {
      // ignore malformed lines
    }
  }
  return true;
}

/**
 * Read one bounded page from a run's NDJSON log. The cursor is the number of
 * non-sentinel events already consumed. Malformed lines and `__end__` do not
 * advance it.
 */
async function readEventLogPage(
  runId: string,
  cursor: number,
  limit: number,
): Promise<{
  events: { kind: string; data: Record<string, unknown> }[];
  nextCursor: number | null;
} | null> {
  const logPath = eventLogPathFor(runId);
  if (!fs.existsSync(logPath)) return null;
  const events: { kind: string; data: Record<string, unknown> }[] = [];
  let seen = 0;
  let hasMore = false;
  const stream = fs.createReadStream(logPath, { encoding: 'utf8' });
  const rl = readline.createInterface({ input: stream, crlfDelay: Infinity });
  for await (const line of rl) {
    if (!line.trim()) continue;
    try {
      const ev = JSON.parse(line) as { kind: string; data: Record<string, unknown> };
      if (ev.kind === '__end__') continue;
      if (seen++ < cursor) continue;
      if (events.length === limit) {
        hasMore = true;
        break;
      }
      events.push(ev);
    } catch {
      // ignore malformed lines
    }
  }
  return {
    events,
    nextCursor: hasMore ? cursor + events.length : null,
  };
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

export default async function experimentsRoutes(
  app: FastifyInstance,
  routeOptions: ExperimentsRouteOptions,
) {
  const limits: ExperimentLimits = { ...DEFAULT_LIMITS, ...routeOptions.limits };
  validateLimits(limits);
  const spawnExperiment = routeOptions.spawnRun ?? spawnRunDefault;
  const runs = new Map<string, RunHandle>();
  const activeRunCount = () =>
    [...runs.values()].filter((handle) => !handle.finished && !handle.paused).length;

  app.addHook('onClose', async () => {
    await Promise.all([...runs.values()].map((handle) => shutdownRun(handle)));
  });

  app.get(
    '',
    {
      schema: {
        querystring: {
          type: 'object',
          additionalProperties: false,
          properties: {
            status: { type: 'string', enum: [...EXPERIMENT_STATUSES] },
            slug: { type: 'string', maxLength: limits.maxSlugLength },
            limit: {
              type: 'integer',
              minimum: 1,
              maximum: limits.maxPageSize,
              default: 20,
            },
            offset: { type: 'integer', minimum: 0, maximum: 1_000_000, default: 0 },
          },
        },
      },
      preValidation: async (req, reply) =>
        rejectUnknownQueryKeys(req.query, ['status', 'slug', 'limit', 'offset'], reply),
    },
    async (req) => {
      const { status, slug, limit = 20, offset = 0 } = req.query as {
        status?: string;
        slug?: string;
        limit?: number;
        offset?: number;
      };
      const { rows, total } = getExperimentsFiltered(
        status || undefined,
        slug || undefined,
        limit,
        offset,
      );
      return {
        experiments: rows.map(rowToExperiment),
        total,
        limit,
        offset,
      };
    },
  );

  app.get(
    '/search',
    {
      schema: {
        querystring: {
          type: 'object',
          additionalProperties: false,
          required: ['q'],
          properties: {
            q: { type: 'string', minLength: 1, maxLength: limits.maxSlugLength },
            limit: {
              type: 'integer',
              minimum: 1,
              maximum: limits.maxPageSize,
              default: 20,
            },
          },
        },
      },
      preValidation: async (req, reply) =>
        rejectUnknownQueryKeys(req.query, ['q', 'limit'], reply),
    },
    async (req) => {
      const { q, limit = 20 } = req.query as { q: string; limit?: number };
      const rows = searchExperiments(q, limit);
      return { experiments: rows.map(rowToExperiment) };
    },
  );

  app.get('/stats', async () => {
    return getExperimentStats();
  });

  app.get('/limits', async () => ({
    max_agents: limits.maxAgents,
    max_ticks: limits.maxTicks,
    max_active_runs: limits.maxActiveRuns,
    max_slug_length: limits.maxSlugLength,
    max_seed: limits.maxSeed,
    min_temperature: limits.minTemperature,
    max_temperature: limits.maxTemperature,
    event_log_max_bytes: config.EVENT_LOG_MAX_BYTES,
    event_log_max_pending_bytes: config.EVENT_LOG_MAX_PENDING_BYTES,
    checkpoint_max_bytes: config.CHECKPOINT_MAX_BYTES,
    replay_default_limit: Math.min(config.REPLAY_DEFAULT_LIMIT, config.REPLAY_MAX_LIMIT),
    replay_max_limit: config.REPLAY_MAX_LIMIT,
  }));

  app.get('/:expId', async (req, reply) => {
    const { expId } = req.params as { expId: string };
    const row = getExperiment(expId);
    if (row) {
      const handle = runs.get(expId);
      return {
        experiment: {
          ...rowToExperiment(row),
          event_persistence: handle ? eventLogState(handle) : null,
        },
      };
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
          event_persistence: eventLogState(handle),
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
          const checkpointError = validateCheckpoint(handle);
          if (checkpointError) {
            handle.failed = true;
            handle.paused = false;
            handle.checkpointPath = null;
            app.log.error({ runId, checkpointError }, 'experiment checkpoint rejected');
            saveExperiment({
              id: runId,
              status: 'error',
              checkpoint_path: null,
              finished_at: new Date().toISOString(),
            });
            return;
          }
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
        if (handle.failed) {
          payload.status = 'error';
        } else if (!handle.cancel) {
          payload.status = 'completed';
        }
        saveExperiment(payload);
      }
    };
  }

  function validateCheckpointPath(checkpointPath: string | null): string | null {
    if (!checkpointPath) return 'checkpoint path was not reported';
    try {
      const size = fs.statSync(checkpointPath).size;
      if (size > config.CHECKPOINT_MAX_BYTES) {
        return `checkpoint exceeds ${config.CHECKPOINT_MAX_BYTES} bytes`;
      }
      return null;
    } catch (error) {
      return error instanceof Error ? error.message : 'checkpoint is not readable';
    }
  }

  function validateCheckpoint(handle: RunHandle): string | null {
    return validateCheckpointPath(handle.checkpointPath);
  }

  // Decrypt keys only immediately before spawning the Python subprocess.
  function defaultApiSettings() {
    const settings = getApiSettingsDecrypted();
    return settings
      ? { api_key: settings.api_key, base_url: settings.base_url, model: settings.model }
      : undefined;
  }

  function namedApiSettings(apiKeyId: number) {
    const key = getApiKeyDecrypted(apiKeyId);
    if (!key?.api_key?.trim()) return undefined;
    return { api_key: key.api_key, base_url: key.base_url, model: key.model };
  }

  function sendCapacityExceeded(reply: FastifyReply) {
    reply.header('Retry-After', '5');
    return reply.status(429).send({
      message: `Active experiment limit reached (${limits.maxActiveRuns})`,
    });
  }

  app.post(
    '',
    {
      schema: createExperimentSchema(limits),
      preValidation: async (req, reply) => {
        const error = createBodyError(req.body, limits);
        if (error) return sendBadRequest(reply, error);
      },
    },
    async (req, reply) => {
      const body = req.body as ExperimentConfig & { seed: number; temperature: number };
      const apiKeyId = body.api_key_id ?? null;
      const apiSettings =
        apiKeyId === null ? defaultApiSettings() : namedApiSettings(apiKeyId);
      if (apiKeyId !== null && !apiSettings) {
        return sendBadRequest(reply, 'api_key_id does not reference a usable key');
      }
      if (activeRunCount() >= limits.maxActiveRuns) {
        return sendCapacityExceeded(reply);
      }

      const runId = crypto.randomBytes(12).toString('hex').slice(0, 12);
      const slug = body.slug.trim();
      const handle = createRunHandle(
        runId,
        slug,
        body.n_agents,
        body.n_ticks,
        body.persona_set,
        body.seed,
        body.temperature,
      );
      runs.set(runId, handle);

      saveExperiment({
        id: runId,
        slug,
        n_agents: body.n_agents,
        n_ticks: body.n_ticks,
        persona_set: body.persona_set,
        status: 'running',
        started_at: new Date().toISOString(),
        finished_at: null,
        result_summary: null,
        seed: body.seed,
        api_key_id: apiKeyId,
      });

      spawnExperiment(handle, makeOnEvent(runId, handle), {
        apiSettings,
        checkpointOut: checkpointPathFor(runId),
        logger: app.log,
      });

      return { run_id: runId };
    },
  );

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
    const checkpointError = validateCheckpointPath(row.checkpoint_path);
    if (checkpointError) {
      reply.status(409);
      return { message: `Checkpoint is not resumable: ${checkpointError}` };
    }
    const apiSettings =
      row.api_key_id == null ? defaultApiSettings() : namedApiSettings(row.api_key_id);
    if (row.api_key_id != null && !apiSettings) {
      reply.status(409);
      return { message: 'The API key selected for this experiment is no longer usable' };
    }
    if (activeRunCount() >= limits.maxActiveRuns) {
      return sendCapacityExceeded(reply);
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

    spawnExperiment(handle, makeOnEvent(expId, handle), {
      apiSettings,
      resumeCheckpoint: row.checkpoint_path,
      checkpointOut: checkpointPathFor(expId),
      logger: app.log,
    });

    return { run_id: expId, resumed: true };
  });

  // Bounded replay page for the front-end player. The numeric cursor counts
  // previously consumed non-sentinel events.
  app.get('/:expId/replay', {
    schema: {
      querystring: {
        type: 'object',
        additionalProperties: false,
        properties: {
          cursor: { type: 'integer', minimum: 0, default: 0 },
          limit: {
            type: 'integer',
            minimum: 1,
            maximum: config.REPLAY_MAX_LIMIT,
            default: Math.min(config.REPLAY_DEFAULT_LIMIT, config.REPLAY_MAX_LIMIT),
          },
        },
      },
    },
  }, async (req, reply) => {
    const { expId } = req.params as { expId: string };
    const { cursor = 0, limit = config.REPLAY_DEFAULT_LIMIT } = req.query as {
      cursor?: number;
      limit?: number;
    };
    const page = await readEventLogPage(expId, cursor, limit);
    if (page === null) {
      reply.status(404);
      return { message: 'No recorded event log for this experiment' };
    }
    return {
      events: page.events,
      total: page.events.length,
      next_cursor: page.nextCursor,
      limit,
    };
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

      let disconnected = false;
      req.raw.once('close', () => {
        disconnected = true;
      });

      // Flush the async writer before taking the live queue boundary. Events
      // arriving after the flush remain in the queue and are streamed below.
      await flushEventLog(handle);
      let idx = handle.queue.length;
      if (wantReplay) {
        const replayed = await replayEventLog(expId, reply);
        if (!replayed) {
          // No NDJSON file (e.g. legacy run) — fall back to capped in-memory
          // history.
          for (const ev of handle.history) {
            if (ev.kind === '__end__') continue;
            if (!(await writeSseChunk(reply.raw, sseFrame(ev.kind, ev.data)))) break;
          }
        }
      }
      if (disconnected) return reply;

      // Throttle live SSE output: within each 100ms window, collapse duplicate
      // high-frequency events of the same kind for the same entity (e.g. one
      // agent_decision per agent per window). The durable NDJSON log still
      // records every event; this only affects the browser-facing stream.
      const throttleWindowMs = 100;
      const lastSent = new Map<string, number>();

      let sending = false;
      const timer = setInterval(async () => {
        if (sending || disconnected) return;
        sending = true;
        const now = Date.now();
        const toSend: Array<{ kind: string; data: Record<string, unknown> }> = [];
        let terminal = false;

        while (idx < handle.queue.length) {
          const ev = handle.queue[idx++];
          if (ev.kind === '__end__') {
            terminal = true;
            break;
          }

          // Key used to collapse duplicates: kind + agent_id when present.
          const entityKey = (ev.data.agent_id ?? ev.data.agentId ?? ev.data.id ?? '').toString();
          const throttleKey = entityKey ? `${ev.kind}:${entityKey}` : ev.kind;
          const last = lastSent.get(throttleKey) ?? 0;

          if (now - last >= throttleWindowMs) {
            toSend.push(ev);
            lastSent.set(throttleKey, now);
          } else {
            // Collapse: keep only the latest event for this key in the window.
            const existingIdx = toSend.findIndex((p) => {
              const pKey = (p.data.agent_id ?? p.data.agentId ?? p.data.id ?? '').toString();
              return (pKey ? `${p.kind}:${pKey}` : p.kind) === throttleKey;
            });
            if (existingIdx >= 0) {
              toSend[existingIdx] = ev;
            } else {
              toSend.push(ev);
            }
            lastSent.set(throttleKey, now);
          }
        }

        for (const ev of toSend) {
          if (!(await writeSseChunk(reply.raw, sseFrame(ev.kind, ev.data)))) {
            disconnected = true;
            break;
          }
        }

        if (!disconnected && (terminal || (handle.finished && idx >= handle.queue.length))) {
          await writeSseChunk(reply.raw, sseFrame('end', {}));
          clearInterval(timer);
          reply.raw.end();
          sending = false;
          return;
        }
        if (!disconnected) {
          disconnected = !(await writeSseChunk(reply.raw, sseFrame('ping', {})));
        }
        if (disconnected) clearInterval(timer);
        sending = false;
      }, 100);

      req.raw.on('close', () => {
        disconnected = true;
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
      if (!reply.raw.destroyed && !reply.raw.writableEnded) {
        await writeSseChunk(reply.raw, sseFrame('end', {}));
        reply.raw.end();
      }
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
        await writeSseChunk(reply.raw, sseFrame('settled', summary));
      } catch {
        await writeSseChunk(reply.raw, sseFrame('settled', {}));
      }
      await writeSseChunk(reply.raw, sseFrame('end', {}));
      reply.raw.end();
      return reply;
    }

    reply.status(404);
    return { message: 'Experiment not found' };
  });
}
