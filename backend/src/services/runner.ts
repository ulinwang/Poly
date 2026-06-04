import { spawn } from 'child_process';
import type { ExperimentRow } from '../types';
import { saveExperiment } from '../db/experiments';

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
  };
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

function onEnd(handle: RunHandle, onPersist: (payload: Partial<ExperimentRow>) => void): void {
  const metrics = handle.finalMetrics;
  const payload: Partial<ExperimentRow> = {
    id: handle.runId,
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
  onPersist(payload);
}

export function spawnRun(
  handle: RunHandle,
  onEvent: (kind: string, data: Record<string, unknown>) => void,
): void {
  const child = spawn('.venv/bin/python3', ['webapp/runner_cli.py'], {
    cwd: '/Users/moonshot/Projects/Poly/polymetl',
  });

  const config = {
    slug: handle.slug,
    n_agents: handle.nAgents,
    n_ticks: handle.nTicks,
    persona_set: handle.personaSet,
    seed: 0,
    temperature: 0.0,
    data_dir: 'data',
  };

  child.stdin.write(JSON.stringify(config));
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
    // eslint-disable-next-line no-console
    console.error('[runner_cli.py stderr]', chunk.trimEnd());
  });

  const cancelCheck = setInterval(() => {
    if (handle.cancel) {
      clearInterval(cancelCheck);
      child.kill('SIGTERM');
    }
  }, 250);

  child.on('error', (err) => {
    clearInterval(cancelCheck);
    if (!handle.finished) {
      onEvent('error', { message: err.message });
      handle.finished = true;
      onEvent('__end__', {});
    }
  });

  child.on('exit', (code) => {
    clearInterval(cancelCheck);
    if (!handle.finished) {
      if (code !== 0) {
        onEvent('error', { message: `process exited with code ${code}` });
      }
      handle.finished = true;
      onEvent('__end__', {});
    }
  });
}
