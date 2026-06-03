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
  const totalTicks = handle.nTicks;
  let tick = 0;

  const interval = setInterval(() => {
    if (handle.cancel) {
      clearInterval(interval);
      handle.finished = true;
      onEvent('__end__', {});
      return;
    }

    tick += 1;
    const yesMid = 0.4 + Math.random() * 0.2;
    onEvent('tick', {
      tick,
      yesMid,
      fills: Math.floor(Math.random() * 10),
      actions: Math.floor(Math.random() * 20),
    });
    onEvent('tick_finished', { tick, elapsed_s: 0.25 + Math.random() * 0.5 });

    if (tick >= totalTicks) {
      clearInterval(interval);
      const finalYesMid = 0.4 + Math.random() * 0.2;
      onEvent('settled', {
        yes_mid_final: finalYesMid,
        n_fills: Math.floor(Math.random() * 100),
        n_actions: Math.floor(Math.random() * 200),
        total_ticks: totalTicks,
      });
      handle.finished = true;
      onEvent('__end__', {});
    }
  }, 300);
}
