import { spawn } from 'child_process';
import type { ChildProcessWithoutNullStreams } from 'child_process';
import { config } from '../config';
// import type { ExperimentRow } from '../types'; // available when needed

export interface RunHandle {
  runId: string;
  slug: string;
  nAgents: number;
  nTicks: number;
  personaSet: string;
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
}

const HISTORY_CAP = 2000;

export function createRunHandle(
  runId: string,
  slug: string,
  nAgents: number,
  nTicks: number,
  personaSet: string,
): RunHandle {
  return {
    runId,
    slug,
    nAgents,
    nTicks,
    personaSet,
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
  };
}

/** Default checkpoint location for a run id (under DATA_DIR/checkpoints). */
export function checkpointPathFor(runId: string): string {
  return `${config.DATA_DIR}/checkpoints/${runId}.pkl`;
}

export function emitEvent(handle: RunHandle, kind: string, data: Record<string, unknown>): void {
  handle.queue.push({ kind, data });
  if (handle.history.length < HISTORY_CAP) {
    handle.history.push({ kind, data });
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
}

export function spawnRun(
  handle: RunHandle,
  onEvent: (kind: string, data: Record<string, unknown>) => void,
  options?: SpawnOptions | { api_key?: string; base_url?: string; model?: string },
): void {
  // Back-compat: callers may still pass a bare apiSettings object.
  const opts: SpawnOptions =
    options && ('apiSettings' in options || 'resumeCheckpoint' in options || 'checkpointOut' in options)
      ? (options as SpawnOptions)
      : { apiSettings: options as SpawnOptions['apiSettings'] };
  const { apiSettings, resumeCheckpoint, checkpointOut } = opts;

  const child = spawn(config.PYTHON_BIN, ['sim/runner/runner_cli.py'], {
    cwd: config.REPO_ROOT,
  });
  handle.child = child;
  // Reset transient pause state for a fresh spawn (resume clears `paused`).
  handle.paused = false;
  handle.finished = false;

  const payload: Record<string, unknown> = {
    slug: handle.slug,
    n_agents: handle.nAgents,
    n_ticks: handle.nTicks,
    persona_set: handle.personaSet,
    seed: 0,
    temperature: 0.0,
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
        if (event.kind === '__end__') {
          handle.finished = true;
        }
      } catch {
        // ignore malformed lines
      }
    }
  });

  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk: string) => {
    console.error('[runner_cli.py stderr]', chunk.trimEnd());
  });

  let pauseSent = false;
  const cancelCheck = setInterval(() => {
    if (handle.cancel) {
      clearInterval(cancelCheck);
      child.kill('SIGTERM');
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
    if (!handle.finished) {
      onEvent('error', { message: err.message });
      handle.finished = true;
      onEvent('__end__', {});
    }
  });

  child.on('exit', (code) => {
    clearInterval(cancelCheck);
    handle.child = null;
    if (!handle.finished) {
      // A non-zero exit that is not an intentional pause is a real error.
      if (code !== 0 && !handle.paused) {
        onEvent('error', { message: `process exited with code ${code}` });
      }
      handle.finished = true;
      onEvent('__end__', {});
    }
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
