import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useExperimentStore } from '../stores';
import { applyEvent } from '../lib/applyEvent';
import { api } from '../lib/api';

/**
 * Domain events whose only effect is to mutate store state — dispatched
 * uniformly through `applyEvent` (the same mapping the replay player uses). The
 * lifecycle events (done/error/cancelled/paused/end/ping) are handled
 * separately below because they also drive running/connection state.
 */
const SSE_DOMAIN_EVENTS = [
  'run_started',
  'market_resolved',
  'priors_ready',
  'population_built',
  'env_ready',
  'tick_started',
  'agent_decision',
  'tick_metrics',
  'agent_snapshots',
  'agent_decision_error',
  'tick_finished',
  'settled',
  'run_resumed',
] as const;

export function useSSE(runId: string | null, replay: number = 1) {
  const setRunning = useExperimentStore((s) => s.setRunning);
  const setPaused = useExperimentStore((s) => s.setPaused);
  const setError = useExperimentStore((s) => s.setError);

  useEffect(() => {
    if (!runId) return;

    const url = new URL(`/api/v1/experiments/${runId}/events`, window.location.origin);
    url.searchParams.set('replay', String(replay));

    const es = new EventSource(url.toString());
    let connected = false;

    es.onopen = () => {
      connected = true;
      setRunning(true);
    };

    // Pure store-mutating events all flow through the shared dispatcher so the
    // kind→store mapping is defined once (also reused by the replay player).
    for (const kind of SSE_DOMAIN_EVENTS) {
      es.addEventListener(kind, (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        applyEvent(useExperimentStore.getState(), kind, data);
      });
    }

    // ── Lifecycle events: apply the event, then drive connection state ──
    es.addEventListener('done', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      applyEvent(useExperimentStore.getState(), 'done', data);
      setRunning(false);
      es.close();
    });

    es.addEventListener('error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        applyEvent(useExperimentStore.getState(), 'error', data);
      } catch {
        setError('SSE connection error');
      }
      setRunning(false);
    });

    es.addEventListener('cancelled', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      applyEvent(useExperimentStore.getState(), 'cancelled', data);
      setRunning(false);
      es.close();
    });

    es.addEventListener('paused', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      applyEvent(useExperimentStore.getState(), 'paused', data);
      setRunning(false);
      setPaused(true);
      es.close();
    });

    es.addEventListener('end', () => {
      setRunning(false);
      es.close();
    });

    es.addEventListener('ping', () => {
      // keep-alive, do nothing
    });

    es.onerror = () => {
      if (connected) {
        console.warn('SSE connection interrupted, retrying...');
      }
    };

    return () => {
      es.close();
    };
  }, [runId, replay, setRunning, setPaused, setError]);
}

export function useDebounce<T>(value: T, delay: number = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}

export function useNowStr() {
  return useCallback(() => {
    const d = new Date();
    return d.toTimeString().slice(0, 8);
  }, []);
}

export function useFormatNumber() {
  return useCallback((n: number | null | undefined): string => {
    if (n === null || n === undefined) return '—';
    if (!Number.isFinite(n)) return '—';
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + 'M';
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'k';
    return n.toFixed(0);
  }, []);
}

// ─────────────────────────────────────────────────────────────────────────
// Replay player
// ─────────────────────────────────────────────────────────────────────────

export type ReplayEvent = { kind: string; data: Record<string, unknown> };
export type ReplaySpeed = 1 | 2 | 4;

export interface ReplayPlayer {
  /** True while the recording is being fetched. */
  loading: boolean;
  /** True when the run has no recorded event log (nothing to replay). */
  empty: boolean;
  /** Whether the timer is currently advancing. */
  playing: boolean;
  /** Playback speed multiplier. */
  speed: ReplaySpeed;
  /** Highest tick applied so far (−1 = only the setup/pre-tick events). */
  currentTick: number;
  /** Highest tick index present in the recording (−1 if no ticks). */
  maxTick: number;
  play: () => void;
  pause: () => void;
  /** Reset to the start (only pre-tick setup applied). */
  restart: () => void;
  /** Apply everything at once and stop at the end. */
  skipToEnd: () => void;
  /** Jump to a tick: reset, then re-apply every event up to and incl. T. */
  seek: (tick: number) => void;
  setSpeed: (s: ReplaySpeed) => void;
}

/** Per-tick base interval (ms) at 1x; divided by the speed multiplier. */
const REPLAY_BASE_INTERVAL_MS = 700;

/**
 * Replay player for a finished run. Fetches the full recorded event log once,
 * groups events by tick, and applies them to the experiment store through the
 * shared `applyEvent` dispatcher — the same mapping the live SSE hook uses, so
 * the replayed UI state is identical to what was shown live.
 *
 * Events that arrive before the first `tick_started` (run_started, env_ready,
 * population_built, …) are bucketed under tick −1 and always applied first.
 * Seeking re-applies from a clean store so state is always consistent with the
 * target tick regardless of direction.
 */
export function useReplayPlayer(runId: string | null, enabled: boolean): ReplayPlayer {
  const resetSimulation = useExperimentStore((s) => s.resetSimulation);

  const [events, setEvents] = useState<ReplayEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(1);
  const [currentTick, setCurrentTick] = useState(-1);

  // Group event indices by tick. -1 holds setup events with no tick field.
  const { ticks, eventsByTick, maxTick } = useMemo(() => {
    const byTick = new Map<number, ReplayEvent[]>();
    for (const ev of events) {
      const raw = ev.data?.tick;
      const tick = typeof raw === 'number' ? raw : -1;
      const bucket = byTick.get(tick);
      if (bucket) bucket.push(ev);
      else byTick.set(tick, [ev]);
    }
    const sorted = [...byTick.keys()].sort((a, b) => a - b);
    const realTicks = sorted.filter((t) => t >= 0);
    return {
      ticks: sorted,
      eventsByTick: byTick,
      maxTick: realTicks.length ? realTicks[realTicks.length - 1] : -1,
    };
  }, [events]);

  // Fetch the recording when entering replay mode.
  useEffect(() => {
    if (!enabled || !runId) return;
    let cancelled = false;
    setLoading(true);
    setEmpty(false);
    setPlaying(false);
    setCurrentTick(-1);
    api.getReplay(runId)
      .then((res) => {
        if (cancelled) return;
        setEvents(res.events);
        setEmpty(res.events.length === 0);
      })
      .catch(() => {
        if (cancelled) return;
        // 404 (no log) or any fetch failure → nothing to replay.
        setEvents([]);
        setEmpty(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [enabled, runId]);

  // Apply every event from (after `fromTick`) up to and including `toTick`.
  // `fromTick = -2` means start from the very beginning (incl. setup bucket).
  const applyRange = useCallback((fromTick: number, toTick: number) => {
    const store = useExperimentStore.getState();
    for (const t of ticks) {
      if (t > fromTick && t <= toTick) {
        for (const ev of eventsByTick.get(t) ?? []) {
          applyEvent(store, ev.kind, ev.data);
        }
      }
    }
  }, [ticks, eventsByTick]);

  const seek = useCallback((tick: number) => {
    const clamped = Math.max(-1, Math.min(tick, maxTick));
    resetSimulation();
    applyRange(-2, clamped); // -2: include the setup bucket (tick -1)
    setCurrentTick(clamped);
    setPlaying(false);
  }, [applyRange, maxTick, resetSimulation]);

  const restart = useCallback(() => {
    resetSimulation();
    applyRange(-2, -1); // setup events only
    setCurrentTick(-1);
    setPlaying(false);
  }, [applyRange, resetSimulation]);

  const skipToEnd = useCallback(() => {
    seek(maxTick);
  }, [seek, maxTick]);

  const play = useCallback(() => {
    if (empty || maxTick < 0) return;
    // Restart from the top if we're already at the end.
    if (currentTick >= maxTick) {
      resetSimulation();
      applyRange(-2, -1);
      setCurrentTick(-1);
    }
    setPlaying(true);
  }, [empty, maxTick, currentTick, resetSimulation, applyRange]);

  const pause = useCallback(() => setPlaying(false), []);

  // On first load (or re-fetch), apply the setup bucket so the page isn't blank.
  const loadedRef = useRef<ReplayEvent[] | null>(null);
  useEffect(() => {
    if (loading || empty || events.length === 0) return;
    if (loadedRef.current === events) return;
    loadedRef.current = events;
    resetSimulation();
    const store = useExperimentStore.getState();
    for (const ev of eventsByTick.get(-1) ?? []) {
      applyEvent(store, ev.kind, ev.data);
    }
    setCurrentTick(-1);
  }, [loading, empty, events, eventsByTick, resetSimulation]);

  // Playback timer: advance one tick per interval.
  useEffect(() => {
    if (!playing) return;
    const interval = REPLAY_BASE_INTERVAL_MS / speed;
    const timer = setInterval(() => {
      setCurrentTick((cur) => {
        const next = cur + 1;
        if (next > maxTick) {
          setPlaying(false);
          return cur;
        }
        const store = useExperimentStore.getState();
        for (const ev of eventsByTick.get(next) ?? []) {
          applyEvent(store, ev.kind, ev.data);
        }
        return next;
      });
    }, interval);
    return () => clearInterval(timer);
  }, [playing, speed, maxTick, eventsByTick]);

  return {
    loading, empty, playing, speed, currentTick, maxTick,
    play, pause, restart, skipToEnd, seek, setSpeed,
  };
}
