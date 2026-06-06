import { useParams } from 'react-router-dom';
import { useEffect, useState, useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { Square, ArrowLeft, X, Pause, Play, SkipForward, RotateCcw } from 'lucide-react';
import { api } from '../lib/api';
import { useExperimentStore } from '../stores';
import { useSSE, useFormatNumber, useReplayPlayer } from '../hooks';
import type { ReplayPlayer, ReplaySpeed } from '../hooks';
import { useI18n } from '../lib/i18n';
import type { Experiment, AgentSnapshot, AgentDecision } from '../types';

/** Deterministic HSL color block from an agent id, used as a tiny "avatar". */
function agentColor(agentId: number): string {
  const hue = (agentId * 47) % 360;
  return `hsl(${hue} 65% 50%)`;
}

export default function ExperimentLive() {
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<number | null>(null);

  const metrics = useExperimentStore((s) => s.metrics);
  const decisions = useExperimentStore((s) => s.decisions);
  const tickMetrics = useExperimentStore((s) => s.tickMetrics);
  const agentSnapshots = useExperimentStore((s) => s.agentSnapshots);
  const running = useExperimentStore((s) => s.running);
  const paused = useExperimentStore((s) => s.paused);
  const error = useExperimentStore((s) => s.error);
  const resetSimulation = useExperimentStore((s) => s.resetSimulation);
  const setRunning = useExperimentStore((s) => s.setRunning);
  const setPaused = useExperimentStore((s) => s.setPaused);

  const [pausePending, setPausePending] = useState(false);

  const formatNumber = useFormatNumber();

  // A finished run (anything that is no longer running) enters replay mode and
  // reads its recorded event log instead of opening a live SSE stream. We only
  // know the status after the experiment loads, so default to "not replay" until
  // then to avoid prematurely treating a fresh/live run as a recording.
  const status = experiment?.status;
  const isReplay = status != null && status !== 'running';

  // Live mode: stream SSE (only when not in replay mode). Replay mode: fetch the
  // recording and drive playback. Both hooks are always called (rules of hooks);
  // each is gated by a flag so only one is active at a time.
  useSSE(isReplay ? null : id || null);
  const replay = useReplayPlayer(id || null, isReplay);

  useEffect(() => {
    if (!id) return;
    resetSimulation();
    setSelectedAgent(null);
    let cancelled = false;
    setLoading(true);
    api.getExperiment(id)
      .then((res) => {
        if (!cancelled) {
          setExperiment(res.experiment);
          // Reflect a persisted paused status when re-opening the page.
          if (res.experiment.status === 'paused') setPaused(true);
        }
      })
      .catch((err) => console.error('Failed to load experiment:', err))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [id, resetSimulation, setPaused]);

  const handleCancel = () => {
    if (!id) return;
    api.cancelExperiment(id).catch(console.error);
  };

  const handlePause = () => {
    if (!id) return;
    setPausePending(true);
    api.pauseExperiment(id)
      .then((res) => {
        if (res.paused) {
          setRunning(false);
          setPaused(true);
        }
      })
      .catch(console.error)
      .finally(() => setPausePending(false));
  };

  const handleResume = () => {
    if (!id) return;
    setPaused(false);
    setRunning(true);
    api.resumeExperiment(id).catch((err) => {
      console.error(err);
      setRunning(false);
      setPaused(true);
    });
  };

  // ── Derived: macro chart from accumulated tick_metrics ────────────────
  const macroData = useMemo(
    () => tickMetrics.map((m) => ({ tick: m.tick, yesMid: m.yes_mid })),
    [tickMetrics],
  );
  const latestTickMetrics = tickMetrics.length > 0 ? tickMetrics[tickMetrics.length - 1] : null;
  const cumFills = useMemo(
    () => tickMetrics.reduce((acc, m) => acc + (m.n_fills || 0), 0),
    [tickMetrics],
  );

  // ── Derived: per-agent latest snapshot + pnl history, id-sorted ───────
  const agentList = useMemo(() => {
    const ids = Object.keys(agentSnapshots).map(Number).sort((a, b) => a - b);
    return ids.map((agentId) => {
      const hist = agentSnapshots[agentId];
      const latest = hist[hist.length - 1];
      return {
        agentId,
        latest,
        pnlHistory: hist.map((h) => h.pnl),
      };
    });
  }, [agentSnapshots]);

  const hasAgents = agentList.length > 0;
  const drawerOpen = selectedAgent !== null;

  // Progress: prefer the live currentTick, fall back to latest macro row.
  const currentTick = metrics.currentTick ?? latestTickMetrics?.tick ?? null;
  const totalTicks = metrics.totalTicks || experiment?.n_ticks || 0;
  const progressLabel = totalTicks > 0 && currentTick !== null
    ? `${currentTick + 1} / ${totalTicks}`
    : currentTick !== null
      ? String(currentTick + 1)
      : '—';

  if (loading) {
    return <div className="text-center py-20 text-surface-400">{t('live.loading')}</div>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <a href="#/experiments" className="p-2 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-800">
            <ArrowLeft className="w-4 h-4 text-surface-500" />
          </a>
          <div>
            <h1 className="text-lg font-bold text-surface-900 dark:text-white">
              {experiment?.slug || id}
            </h1>
            <div className="flex items-center gap-2 text-xs text-surface-400">
              {isReplay && (
                <span className="badge bg-primary-100 text-primary-700 dark:bg-primary-500/15 dark:text-primary-300">
                  {t('replay.badge')}
                </span>
              )}
              <span className={`badge ${running ? 'badge-live' : paused ? 'badge-warn' : 'badge-resolved'}`}>
                {running
                  ? t('live.running')
                  : paused
                    ? t('live.paused')
                    : experiment?.status
                      ? t(`exp.status.${experiment.status}`)
                      : t('live.done')}
              </span>
              <span>
                {experiment?.n_agents} {t('detail.unitAgents')} · {experiment?.n_ticks} {t('detail.unitTicks')}
                {experiment?.seed != null ? ` · ${t('detail.seedLabel', { seed: experiment.seed })}` : ''}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {running && (
            <button
              onClick={handlePause}
              disabled={pausePending}
              className="btn-secondary flex items-center gap-2 disabled:opacity-50"
            >
              <Pause className="w-4 h-4" />
              {pausePending ? t('live.pausing') : t('live.pause')}
            </button>
          )}
          {paused && !running && (
            <button onClick={handleResume} className="btn-secondary flex items-center gap-2 text-primary-600">
              <Play className="w-4 h-4" />
              {t('live.resume')}
            </button>
          )}
          {(running || paused) && (
            <button onClick={handleCancel} className="btn-secondary flex items-center gap-2 text-danger">
              <Square className="w-4 h-4" />
              {t('live.cancel')}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="card p-4 bg-danger/10 border-danger/20 text-danger text-sm">
          {t('live.error', { msg: error })}
        </div>
      )}

      {/* ── Replay player controls (finished runs only) ───────────────── */}
      {isReplay && <ReplayControls replay={replay} />}

      {/* ── Top: horizontally scrollable agent strip ──────────────────── */}
      <AgentStrip
        agents={agentList}
        selectedAgent={selectedAgent}
        onSelect={(aid) => setSelectedAgent((cur) => (cur === aid ? null : aid))}
        hasAgents={hasAgents}
        running={running}
      />

      {/* ── Body: macro (left/full) + agent drawer (right) ────────────── */}
      <div className="flex gap-4 items-start">
        {/* Main: macro market outcome */}
        <div className={`space-y-4 min-w-0 transition-all duration-300 ${drawerOpen ? 'flex-1' : 'w-full'}`}>
          {/* Macro metric cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard
              label={t('live.metric.yesMid')}
              value={latestTickMetrics ? latestTickMetrics.yes_mid.toFixed(3) : metrics.yesMid.toFixed(3)}
            />
            <MetricCard
              label={t('live.metric.parityGap')}
              value={latestTickMetrics ? latestTickMetrics.parity_gap.toFixed(3) : '—'}
            />
            <MetricCard label={t('live.metric.cumulativeFills')} value={formatNumber(cumFills || metrics.nFills)} />
            <MetricCard label={t('live.metric.tickProgress')} value={progressLabel} />
          </div>

          {/* Macro chart: yes_mid over ticks */}
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3">
              {t('live.chartTitle')}
            </h3>
            {macroData.length === 0 ? (
              <EmptyState
                running={running}
                idle={t('live.macroIdle')}
                live={t('live.macroLive')}
              />
            ) : (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={macroData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="tick" tick={{ fontSize: 12 }} />
                    <YAxis domain={[0, 1]} tick={{ fontSize: 12 }} />
                    <Tooltip formatter={(v) => Number(v).toFixed(3)} />
                    <Line
                      type="monotone"
                      dataKey="yesMid"
                      name="YES mid"
                      stroke="#0d9488"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>

        {/* Right drawer: selected agent detail */}
        {drawerOpen && selectedAgent !== null && (
          <AgentDrawer
            agentId={selectedAgent}
            snapshot={agentSnapshots[selectedAgent]?.[agentSnapshots[selectedAgent].length - 1] ?? null}
            decisions={decisions.filter((d) => d.agent_id === selectedAgent)}
            onClose={() => setSelectedAgent(null)}
            formatNumber={formatNumber}
          />
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Agent strip
// ─────────────────────────────────────────────────────────────────────────

interface AgentStripItem {
  agentId: number;
  latest: AgentSnapshot;
  pnlHistory: number[];
}

function AgentStrip({
  agents, selectedAgent, onSelect, hasAgents, running,
}: {
  agents: AgentStripItem[];
  selectedAgent: number | null;
  onSelect: (agentId: number) => void;
  hasAgents: boolean;
  running: boolean;
}) {
  const { t } = useI18n();
  if (!hasAgents) {
    return (
      <div className="card p-4">
        <EmptyState
          running={running}
          idle={t('live.agentsIdle')}
          live={t('live.agentsLive')}
        />
      </div>
    );
  }

  return (
    <div className="card p-3">
      <div className="flex gap-3 overflow-x-auto pb-1">
        {agents.map((a) => {
          const pnl = a.latest.pnl;
          const selected = selectedAgent === a.agentId;
          return (
            <button
              key={a.agentId}
              onClick={() => onSelect(a.agentId)}
              className={`shrink-0 w-40 text-left rounded-lg border p-3 transition-colors ${
                selected
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-500/10'
                  : 'border-surface-200 dark:border-surface-700 hover:border-primary-300 dark:hover:border-primary-600 bg-surface-50 dark:bg-surface-800/50'
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className="w-7 h-7 rounded-md shrink-0"
                  style={{ background: agentColor(a.agentId) }}
                  aria-hidden
                />
                <div className="min-w-0">
                  <div className="font-mono text-sm font-semibold text-surface-900 dark:text-white">
                    A{a.agentId}
                  </div>
                  <div className="text-[10px] text-surface-500 truncate">{a.latest.persona}</div>
                </div>
              </div>
              <div className={`mt-2 text-sm font-bold ${pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}
              </div>
              <Sparkline values={a.pnlHistory} positive={pnl >= 0} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Tiny inline SVG sparkline for a pnl series. */
function Sparkline({ values, positive }: { values: number[]; positive: boolean }) {
  const { t } = useI18n();
  const W = 130;
  const H = 28;
  if (values.length < 2) {
    return <div className="mt-2 h-7 text-[10px] text-surface-400">{t('live.noHistory')}</div>;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = W / (values.length - 1);
  const points = values
    .map((v, i) => {
      const x = i * stepX;
      const y = H - ((v - min) / span) * H;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full" preserveAspectRatio="none">
      <polyline
        points={points}
        fill="none"
        stroke={positive ? '#10b981' : '#ef4444'}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Agent drawer
// ─────────────────────────────────────────────────────────────────────────

function AgentDrawer({
  agentId, snapshot, decisions, onClose, formatNumber,
}: {
  agentId: number;
  snapshot: AgentSnapshot | null;
  decisions: AgentDecision[];
  onClose: () => void;
  formatNumber: (n: number | null | undefined) => string;
}) {
  const { t } = useI18n();
  // Latest tick first.
  const ordered = useMemo(
    () => [...decisions].sort((a, b) => b.tick - a.tick),
    [decisions],
  );

  return (
    <aside className="w-96 shrink-0 card p-4 max-h-[80vh] overflow-y-auto">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span
            className="w-8 h-8 rounded-md"
            style={{ background: agentColor(agentId) }}
            aria-hidden
          />
          <div>
            <div className="font-mono text-base font-bold text-surface-900 dark:text-white">
              A{agentId}
            </div>
            {snapshot && (
              <div className="text-xs text-surface-500">{snapshot.persona}</div>
            )}
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-800"
          aria-label={t('common.close')}
        >
          <X className="w-4 h-4 text-surface-500" />
        </button>
      </div>

      {/* State from latest snapshot */}
      {snapshot ? (
        <div className="grid grid-cols-2 gap-2 mb-4">
          <StatCell label={t('live.stat.pnl')} value={`${snapshot.pnl >= 0 ? '+' : ''}${snapshot.pnl.toFixed(2)}`} accent={snapshot.pnl >= 0 ? 'pos' : 'neg'} />
          <StatCell label={t('live.stat.cash')} value={`$${formatNumber(snapshot.cash)}`} />
          <StatCell label={t('live.stat.posYes')} value={snapshot.pos_yes.toFixed(2)} />
          <StatCell label={t('live.stat.posNo')} value={snapshot.pos_no.toFixed(2)} />
          <StatCell
            label={t('live.stat.beliefYes')}
            value={snapshot.belief_yes !== null ? snapshot.belief_yes.toFixed(3) : '—'}
          />
          <StatCell
            label={t('live.stat.reserved')}
            value={`$${formatNumber(snapshot.cash_reserved)}`}
          />
        </div>
      ) : (
        <div className="text-xs text-surface-400 mb-4">{t('live.noSnapshot')}</div>
      )}

      {/* Thinking log: reasoning per tick, newest first */}
      <h4 className="text-xs font-semibold uppercase tracking-wide text-surface-500 mb-2">
        {t('live.thinking', { count: ordered.length })}
      </h4>
      {ordered.length === 0 ? (
        <div className="text-xs text-surface-400">{t('live.noDecisions')}</div>
      ) : (
        <div className="space-y-2">
          {ordered.map((d) => (
            <div
              key={d.id}
              className="p-3 rounded-lg bg-surface-50 dark:bg-surface-800/50 text-sm"
            >
              <div className="flex items-center gap-2 text-xs text-surface-500 flex-wrap">
                <span className="font-semibold">t{d.tick + 1}</span>
                {d.persona_type && (
                  <span className="badge bg-surface-200 text-surface-600">{d.persona_type}</span>
                )}
                {d.api_latency_ms != null && <span className="ml-auto">{d.api_latency_ms}ms</span>}
              </div>
              <div className="mt-1 font-medium text-surface-800 dark:text-surface-200">
                {d.order_type}
                {d.side && ` ${d.side} ${d.outcome}`}
                {d.price > 0 && ` @ ${d.price.toFixed(3)}`}
                {d.size_usd > 0 && ` · $${formatNumber(d.size_usd)}`}
              </div>
              {d.reasoning && (
                <p className="mt-1 text-xs text-surface-600 dark:text-surface-400 whitespace-pre-wrap">
                  {d.reasoning}
                </p>
              )}
              {d.api_error && (
                <p className="mt-1 text-xs text-danger">{d.api_error}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}

function StatCell({ label, value, accent }: { label: string; value: string; accent?: 'pos' | 'neg' }) {
  const valueClass =
    accent === 'pos' ? 'text-success' : accent === 'neg' ? 'text-danger' : 'text-surface-900 dark:text-white';
  return (
    <div className="rounded-lg bg-surface-50 dark:bg-surface-800/50 p-2">
      <div className="text-[10px] text-surface-400">{label}</div>
      <div className={`text-sm font-bold mt-0.5 ${valueClass}`}>{value}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Replay controls
// ─────────────────────────────────────────────────────────────────────────

const REPLAY_SPEEDS: ReplaySpeed[] = [1, 2, 4];

function ReplayControls({ replay }: { replay: ReplayPlayer }) {
  const { t } = useI18n();

  if (replay.loading) {
    return (
      <div className="card p-4 text-center text-sm text-surface-400">
        {t('replay.loading')}
      </div>
    );
  }
  if (replay.empty) {
    return (
      <div className="card p-4 text-center text-sm text-surface-400">
        {t('replay.empty')}
      </div>
    );
  }

  // Scrubber operates over ticks [-1 .. maxTick]; -1 = setup-only.
  const sliderMax = Math.max(replay.maxTick, 0);
  const sliderValue = Math.max(replay.currentTick, 0);
  const tickLabel = t('replay.tickOf', {
    current: replay.currentTick + 1,
    total: replay.maxTick + 1,
  });

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        {replay.playing ? (
          <button onClick={replay.pause} className="btn-secondary flex items-center gap-2">
            <Pause className="w-4 h-4" />
            {t('replay.pause')}
          </button>
        ) : (
          <button onClick={replay.play} className="btn-secondary flex items-center gap-2 text-primary-600">
            <Play className="w-4 h-4" />
            {t('replay.play')}
          </button>
        )}
        <button onClick={replay.restart} className="btn-secondary flex items-center gap-2" title={t('replay.restart')}>
          <RotateCcw className="w-4 h-4" />
          <span className="hidden sm:inline">{t('replay.restart')}</span>
        </button>
        <button onClick={replay.skipToEnd} className="btn-secondary flex items-center gap-2" title={t('replay.skipToEnd')}>
          <SkipForward className="w-4 h-4" />
          <span className="hidden sm:inline">{t('replay.skipToEnd')}</span>
        </button>

        {/* Speed selector */}
        <div className="flex items-center gap-1 ml-2">
          <span className="text-xs text-surface-400">{t('replay.speed')}</span>
          {REPLAY_SPEEDS.map((s) => (
            <button
              key={s}
              onClick={() => replay.setSpeed(s)}
              className={`px-2 py-1 rounded-md text-xs font-medium transition-colors ${
                replay.speed === s
                  ? 'bg-primary-500 text-white'
                  : 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-300 hover:bg-surface-200 dark:hover:bg-surface-700'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>

        <span className="ml-auto text-xs font-mono text-surface-500">{tickLabel}</span>
      </div>

      {/* Scrubber: drag to seek by tick */}
      <input
        type="range"
        min={0}
        max={sliderMax}
        step={1}
        value={sliderValue}
        onChange={(e) => replay.seek(Number(e.target.value))}
        className="w-full accent-primary-500"
        aria-label={t('replay.progress')}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Shared bits
// ─────────────────────────────────────────────────────────────────────────

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-surface-400">{label}</div>
      <div className="text-xl font-bold text-surface-900 dark:text-white mt-1">{value}</div>
    </div>
  );
}

function EmptyState({ running, idle, live }: { running: boolean; idle: string; live: string }) {
  return (
    <div className="text-center py-10 text-surface-400 text-sm">
      {running ? live : idle}
    </div>
  );
}
