import { useEffect, useState, useCallback } from 'react';
import { useExperimentStore } from '../stores';

export function useSSE(runId: string | null, replay: number = 1) {
  const addEvent = useExperimentStore((s) => s.addEvent);
  const setRunning = useExperimentStore((s) => s.setRunning);
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

    es.addEventListener('run_started', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'run_started', data });
    });

    es.addEventListener('market_resolved', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'market_resolved', data });
    });

    es.addEventListener('priors_ready', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'priors_ready', data });
    });

    es.addEventListener('population_built', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'population_built', data });
    });

    es.addEventListener('env_ready', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'env_ready', data });
    });

    es.addEventListener('tick_started', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'tick_started', data });
    });

    es.addEventListener('agent_decision', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'agent_decision', data });
    });

    es.addEventListener('agent_decision_error', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'agent_decision_error', data });
    });

    es.addEventListener('tick_finished', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'tick_finished', data });
    });

    es.addEventListener('settled', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'settled', data });
    });

    es.addEventListener('done', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'done', data });
      setRunning(false);
      es.close();
    });

    es.addEventListener('error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        addEvent({ event: 'error', data });
        setError(data.message || 'Unknown error');
      } catch {
        setError('SSE connection error');
      }
      setRunning(false);
    });

    es.addEventListener('cancelled', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'cancelled', data });
      setRunning(false);
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
  }, [runId, replay, addEvent, setRunning, setError]);
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
