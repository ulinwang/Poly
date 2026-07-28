import { spawn } from 'child_process';
import type { ChildProcessWithoutNullStreams } from 'child_process';
import fs from 'fs';
import path from 'path';
import { config } from '../config.js';
import type { FastifyBaseLogger } from 'fastify';
// import type { ExperimentRow } from '../types/index.js'; // available when needed

export interface RunHandle {
  runId: string;
  slug: string;
  nAgents: number;
  nTicks: number;
  personaSet: string;
  /** RNG seed for this run (reproducibility). Defaults to 0. */
  seed: number;
  /** LLM sampling temperature for this run. Defaults to 0. */
  temperature: number;
  queue: Array<{ kind: string; data: Record<string, unknown> }>;
  history: Array<{ kind: string; data: Record<string, unknown> }>;
  cancel: boolean;
  finished: boolean;
  startedAt: number;
  finalMetrics: Record<string, unknown>;
  tickElapsedTotal: number;
  tickCount: number;
  /** True once the Python process emitted `paused` and checkpointed. */
  paused: boolean;
  /** Set when a pause has been requested (SIGUSR1 sent), before `paused`. */
  pauseRequested: boolean;
  /** Path to the checkpoint pickle, set on `paused`. */
  checkpointPath: string | null;
  /** Live child process, used to deliver SIGUSR1 (pause) / SIGTERM (cancel). */
  child: ChildProcessWithoutNullStreams | null;
  /** Structured logger inherited from the Fastify process, when available. */
  logger: Pick<FastifyBaseLogger, 'info' | 'warn' | 'error'> | null;
  /** True when the runner failed before producing a normal terminal event. */
  failed: boolean;
}

const HISTORY_CAP = 2000;

export function createRunHandle(
  runId: string,
  slug: string,
  nAgents: number,
  nTicks: number,
  personaSet: string,
  seed = 0,
  temperature = 0,
): RunHandle {
  return {
    runId,
    slug,
    nAgents,
    nTicks,
    personaSet,
    seed,
    temperature,
    queue: [],
    history: [],
    cancel: false,
    finished: false,
    startedAt: Date.now() / 1000,
    finalMetrics: {},
    tickElapsedTotal: 0,
    tickCount: 0,
    paused: false,
    pauseRequested: false,
    checkpointPath: null,
    child: null,
    logger: null,
    failed: false,
  };
}

/** Default checkpoint location for a run id (under DATA_DIR/checkpoints). */
export function checkpointPathFor(runId: string): string {
  return `${config.DATA_DIR}/checkpoints/${runId}.pkl`;
}

/**
 * NDJSON event-log location for a run id (under DATA_DIR/runs). Every emitted
 * event is appended here as one JSON object per line so the full history
 * survives the in-memory HISTORY_CAP truncation and server restarts. Resumed
 * runs append to the same file.
 */
export function eventLogPathFor(runId: string): string {
  return path.join(config.DATA_DIR, 'runs', `${runId}.ndjson`);
}

export function emitEvent(handle: RunHandle, kind: string, data: Record<string, unknown>): void {
  handle.queue.push({ kind, data });
  if (handle.history.length < HISTORY_CAP) {
    handle.history.push({ kind, data });
  }
  // Persist every event to NDJSON so the full history is durable (not capped,
  // survives restart). Synchronous append is fine: event volume is modest and
  // ordering must match the in-memory queue. Failures must not crash the run.
  try {
    const logPath = eventLogPathFor(handle.runId);
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, JSON.stringify({ kind, data }) + '\n');
  } catch (err) {
    handle.logger?.error(
      {
        runId: handle.runId,
        errorType: err instanceof Error ? err.name : 'UnknownError',
      },
      'failed to append experiment event log',
    );
  }
  if (kind === 'settled') {
    handle.finalMetrics = data;
  } else if (kind === 'tick_finished') {
    handle.tickElapsedTotal += (data.elapsed_s as number) || 0;
    handle.tickCount += 1;
  }
}

// onEnd helper available for future use if persisting from runner directly

export interface SpawnOptions {
  apiSettings?: { api_key?: string; base_url?: string; model?: string };
  /** When set, resume from this checkpoint instead of starting fresh. */
  resumeCheckpoint?: string;
  /** Where the Python side writes its checkpoint when paused. */
  checkpointOut?: string;
  /** Structured lifecycle logger. API keys and runner stderr are never logged. */
  logger?: Pick<FastifyBaseLogger, 'info' | 'warn' | 'error'>;
}

export function spawnRun(
  handle: RunHandle,
  onEvent: (kind: string, data: Record<string, unknown>) => void,
  options?: SpawnOptions | { api_key?: string; base_url?: string; model?: string },
): void {
  // Back-compat: callers may still pass a bare apiSettings object.
  const opts: SpawnOptions =
    options &&
    ('apiSettings' in options ||
      'resumeCheckpoint' in options ||
      'checkpointOut' in options ||
      'logger' in options)
      ? (options as SpawnOptions)
      : { apiSettings: options as SpawnOptions['apiSettings'] };
  const { apiSettings, resumeCheckpoint, checkpointOut, logger } = opts;
  handle.logger = logger ?? null;
  handle.failed = false;

  const child = spawn(config.PYTHON_BIN, ['sim/runner/runner_cli.py'], {
    cwd: config.REPO_ROOT,
  });
  logger?.info(
    {
      runId: handle.runId,
      nAgents: handle.nAgents,
      nTicks: handle.nTicks,
      personaSet: handle.personaSet,
      resumed: Boolean(resumeCheckpoint),
    },
    'experiment runner started',
  );
  handle.child = child;
  // Reset transient pause state for a fresh spawn (resume clears `paused`).
  handle.paused = false;
  handle.finished = false;

  const payload: Record<string, unknown> = {
    slug: handle.slug,
    n_agents: handle.nAgents,
    n_ticks: handle.nTicks,
    persona_set: handle.personaSet,
    seed: handle.seed,
    temperature: handle.temperature,
    data_dir: 'data',
  };
  if (checkpointOut) payload.checkpoint_out = checkpointOut;
  if (resumeCheckpoint) payload.resume_checkpoint = resumeCheckpoint;
  if (apiSettings?.api_key) payload.api_key = apiSettings.api_key;
  if (apiSettings?.base_url) payload.base_url = apiSettings.base_url;
  if (apiSettings?.model) payload.model = apiSettings.model;

  child.stdin.write(JSON.stringify(payload));
  child.stdin.end();

  let buffer = '';

  child.stdout.setEncoding('utf8');
  child.stdout.on('data', (chunk: string) => {
    buffer += chunk;
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const event = JSON.parse(line) as { kind: string; data: Record<string, unknown> };
        onEvent(event.kind, event.data);
        if (event.kind === 'paused') {
          handle.paused = true;
          handle.checkpointPath = (event.data.checkpoint as string) ?? handle.checkpointPath;
        }
        if (event.kind === 'error') {
          handle.failed = true;
          logger?.error(
            { runId: handle.runId },
            'experiment runner reported a failure event',
          );
        }
        if (event.kind === '__end__') {
          handle.finished = true;
        }
      } catch {
        // ignore malformed lines
      }
    }
  });

  child.stderr.setEncoding('utf8');
  let stderrBytes = 0;
  child.stderr.on('data', (chunk: string) => {
    // stderr may contain provider responses or prompt fragments. Track only
    // its size and log lifecycle metadata after exit.
    stderrBytes += Buffer.byteLength(chunk);
  });

  let pauseSent = false;
  // Cancel escalation: SIGTERM first (lets Python emit `cancelled` and clean
  // up), then SIGKILL if it's still alive after a short grace period. The
  // Python side checks the cancel flag cooperatively between agents, so while
  // it's blocked in a long LLM call SIGTERM alone can take tens of seconds;
  // SIGKILL guarantees the run stops promptly. Cancel discards the run (no
  // checkpoint), so a hard kill is safe.
  let killDeadline = 0;
  const cancelCheck = setInterval(() => {
    if (handle.cancel) {
      if (killDeadline === 0) {
        child.kill('SIGTERM');
        killDeadline = Date.now() + 3000;
      } else if (Date.now() >= killDeadline) {
        clearInterval(cancelCheck);
        child.kill('SIGKILL');
      }
    } else if (handle.pauseRequested && !pauseSent) {
      // SIGUSR1 -> Python checkpoints at the next tick boundary, emits
      // `paused`, then exits cleanly.
      pauseSent = true;
      child.kill('SIGUSR1');
    }
  }, 250);

  child.on('error', (err) => {
    clearInterval(cancelCheck);
    handle.child = null;
    handle.failed = true;
    logger?.error(
      {
        runId: handle.runId,
        errorType: err.name,
        errorCode: 'code' in err ? err.code : undefined,
      },
      'experiment runner process error',
    );
    if (!handle.finished) {
      onEvent('error', { message: err.message });
      handle.finished = true;
      onEvent('__end__', {});
    }
  });

  child.on('exit', (code, signal) => {
    clearInterval(cancelCheck);
    handle.child = null;
    if (stderrBytes > 0) {
      logger?.warn(
        { runId: handle.runId, stderrBytes },
        'experiment runner wrote diagnostic output',
      );
    }
    if (!handle.finished) {
      // A non-zero exit that is not an intentional pause OR cancel is a real
      // error. A cancelled run exits non-zero when force-killed (SIGKILL),
      // which is expected — don't surface it as an error.
      if (code !== 0 && !handle.paused && !handle.cancel) {
        handle.failed = true;
        logger?.error(
          { runId: handle.runId, exitCode: code, signal },
          'experiment runner exited unsuccessfully',
        );
        onEvent('error', { message: `process exited with code ${code}` });
      }
      if (handle.cancel) {
        onEvent('cancelled', {});
      }
      handle.finished = true;
      onEvent('__end__', {});
    }
    logger?.info(
      {
        runId: handle.runId,
        status: handle.failed
          ? 'error'
          : handle.cancel
            ? 'cancelled'
            : handle.paused
              ? 'paused'
              : 'completed',
      },
      'experiment runner stopped',
    );
  });
}

/**
 * Request a pause: flag the handle so the spawn loop sends SIGUSR1 to the
 * Python process, which checkpoints at the next tick boundary and emits a
 * `paused` event. Returns false if there is no live child to signal.
 */
export function pauseRun(handle: RunHandle): boolean {
  if (!handle.child || handle.finished) return false;
  handle.pauseRequested = true;
  return true;
}
