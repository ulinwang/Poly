import { useEffect, useState, useCallback } from 'react';
import { useExperimentStore } from '../stores';

export function useSSE(runId: string | null, replay: number = 1) {
  const addEvent = useExperimentStore((s) => s.addEvent);
  const addDecision = useExperimentStore((s) => s.addDecision);
  const addTickLog = useExperimentStore((s) => s.addTickLog);
  const setMetrics = useExperimentStore((s) => s.setMetrics);
  const setRunning = useExperimentStore((s) => s.setRunning);
  const setError = useExperimentStore((s) => s.setError);

  const nowStr = useCallback(() => {
    const d = new Date();
    return d.toTimeString().slice(0, 8);
  }, []);

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
      addTickLog({ id: Date.now(), time: nowStr(), label: 'start', msg: `Run started: ${data.slug}`, kind: 'info' });
    });

    es.addEventListener('market_resolved', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'market_resolved', data });
      addTickLog({ id: Date.now(), time: nowStr(), label: 'market', msg: data.question || 'Market resolved', kind: 'info' });
    });

    es.addEventListener('priors_ready', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'priors_ready', data });
      addTickLog({ id: Date.now(), time: nowStr(), label: 'priors', msg: `Priors ready: μ=${data.signal_mu?.toFixed(3) || '?'}`, kind: 'info' });
    });

    es.addEventListener('population_built', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'population_built', data });
      addTickLog({ id: Date.now(), time: nowStr(), label: 'agents', msg: `${data.n_agents} agents built`, kind: 'info' });
    });

    es.addEventListener('env_ready', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'env_ready', data });
      setMetrics({
        yesMid: data.yes_mid_post_seed ?? 0.5,
        totalTicks: data.n_ticks ?? 0,
      });
      addTickLog({ id: Date.now(), time: nowStr(), label: 'env', msg: `Env ready: YES=${data.yes_mid_post_seed?.toFixed(3) || '?'}`, kind: 'info' });
    });

    es.addEventListener('tick_started', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'tick_started', data });
      setMetrics({ currentTick: data.tick });
    });

    es.addEventListener('agent_decision', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'agent_decision', data });
      addDecision({
        id: Date.now() + Math.random(),
        agent_id: data.agent_id,
        tick: data.tick,
        persona_type: data.persona_type,
        order_type: data.order_type,
        side: data.side,
        outcome: data.outcome,
        price: data.price,
        size_usd: data.size_usd,
        reasoning: data.reasoning,
        api_latency_ms: data.api_latency_ms,
        api_error: data.api_error,
      });
    });

    es.addEventListener('agent_decision_error', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'agent_decision_error', data });
      addTickLog({
        id: Date.now(),
        time: nowStr(),
        label: 'dec_err',
        msg: `Agent ${data.agent_id} tick ${data.tick}: ${data.message}`,
        kind: 'error',
      });
    });

    es.addEventListener('tick_finished', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'tick_finished', data });
      const yesMid = data.yes_mid ?? 0.5;
      setMetrics({
        yesMid,
        nFills: data.n_fills ?? 0,
        nActions: data.n_actions ?? 0,
        lastTickElapsed: data.elapsed_s ?? 0,
      });
      // Append to history
      const store = useExperimentStore.getState();
      const history = [...store.metrics.yesMidHistory, yesMid];
      if (history.length > 500) history.shift();
      setMetrics({ yesMidHistory: history });
      addTickLog({
        id: Date.now(),
        time: nowStr(),
        label: 'tick',
        msg: `Tick ${data.tick}: YES=${yesMid.toFixed(3)} fills=${data.n_fills} actions=${data.n_actions}`,
        kind: 'info',
      });
    });

    es.addEventListener('settled', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'settled', data });
      setMetrics({
        yesMid: data.yes_mid_final ?? 0.5,
        nFills: data.n_fills ?? 0,
        nActions: data.n_actions ?? 0,
      });
      addTickLog({
        id: Date.now(),
        time: nowStr(),
        label: 'settled',
        msg: `Settled: YES=${data.yes_mid_final?.toFixed(3) || '?'} fills=${data.n_fills}`,
        kind: 'info',
      });
    });

    es.addEventListener('done', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'done', data });
      setRunning(false);
      addTickLog({ id: Date.now(), time: nowStr(), label: 'done', msg: 'Simulation complete', kind: 'info' });
      es.close();
    });

    es.addEventListener('error', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        addEvent({ event: 'error', data });
        setError(data.message || 'Unknown error');
        addTickLog({ id: Date.now(), time: nowStr(), label: 'error', msg: data.message, kind: 'error' });
      } catch {
        setError('SSE connection error');
      }
      setRunning(false);
    });

    es.addEventListener('cancelled', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      addEvent({ event: 'cancelled', data });
      setRunning(false);
      addTickLog({ id: Date.now(), time: nowStr(), label: 'cancel', msg: `Cancelled at tick ${data.tick ?? '?'}`, kind: 'warn' });
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
  }, [runId, replay, addEvent, addDecision, addTickLog, setMetrics, setRunning, setError, nowStr]);
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
