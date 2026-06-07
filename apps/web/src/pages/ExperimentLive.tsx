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
import type {
  Experiment, AgentSnapshot, AgentDecision,
  ForumPost, ForumComment, FollowEdge,
} from '../types';

/** The three top-level observation tabs. */
type ObsTab = 'market' | 'forum' | 'social';

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
  const [tab, setTab] = useState<ObsTab>('market');

  const metrics = useExperimentStore((s) => s.metrics);
  const decisions = useExperimentStore((s) => s.decisions);
  const tickMetrics = useExperimentStore((s) => s.tickMetrics);
  const agentSnapshots = useExperimentStore((s) => s.agentSnapshots);
  const forumPosts = useExperimentStore((s) => s.forumPosts);
  const forumComments = useExperimentStore((s) => s.forumComments);
  const follows = useExperimentStore((s) => s.follows);
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
          {/* Pausable whenever the experiment is actually running (by status),
              not just when the transient SSE `running` flag is set — a flaky
              stream shouldn't hide the control. */}
          {(running || status === 'running') && !paused && (
            <button
              onClick={handlePause}
              disabled={pausePending}
              className="btn-secondary flex items-center gap-2 disabled:opacity-50"
            >
              <Pause className="w-4 h-4" />
              {pausePending ? t('live.pausing') : t('live.pause')}
            </button>
          )}
          {paused && (
            <button onClick={handleResume} className="btn-secondary flex items-center gap-2 text-primary-600">
              <Play className="w-4 h-4" />
              {t('live.resume')}
            </button>
          )}
          {(running || paused || status === 'running') && (
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
      {/* Status badge / replay / pause-resume above the tabs: they apply to
          all three observation tabs (Market / Forum / Social). */}
      {isReplay && <ReplayControls replay={replay} />}

      {/* ── Top tab switcher: Market / Forum / Social ─────────────────── */}
      <ObsTabs tab={tab} onChange={setTab} />

      {tab === 'market' && (
        <>
          {/* ── Top: horizontally scrollable agent strip ──────────────── */}
          <AgentStrip
            agents={agentList}
            selectedAgent={selectedAgent}
            onSelect={(aid) => setSelectedAgent((cur) => (cur === aid ? null : aid))}
            hasAgents={hasAgents}
            running={running}
          />

          {/* ── Body: macro (left/full) + agent drawer (right) ────────── */}
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
        </>
      )}

      {tab === 'forum' && (
        <ForumTab posts={forumPosts} comments={forumComments} follows={follows} />
      )}

      {tab === 'social' && (
        <SocialTab posts={forumPosts} follows={follows} />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Tab switcher
// ─────────────────────────────────────────────────────────────────────────

function ObsTabs({ tab, onChange }: { tab: ObsTab; onChange: (t: ObsTab) => void }) {
  const { t } = useI18n();
  const items: { key: ObsTab; label: string }[] = [
    { key: 'market', label: t('tab.market') },
    { key: 'forum', label: t('tab.forum') },
    { key: 'social', label: t('tab.social') },
  ];
  return (
    <div className="flex gap-1 border-b border-surface-200 dark:border-surface-700">
      {items.map((it) => {
        const active = tab === it.key;
        return (
          <button
            key={it.key}
            onClick={() => onChange(it.key)}
            className={`px-4 py-2 -mb-px text-sm font-medium border-b-2 transition-colors ${
              active
                ? 'border-primary-500 text-primary-600 dark:text-primary-300'
                : 'border-transparent text-surface-500 hover:text-surface-700 dark:hover:text-surface-300'
            }`}
          >
            {it.label}
          </button>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Forum tab — Twitter-like feed of posts (newest tick first) with nested
// comments per post and a small "followed author" marker.
// ─────────────────────────────────────────────────────────────────────────

function ForumTab({
  posts, comments, follows,
}: {
  posts: ForumPost[];
  comments: ForumComment[];
  follows: FollowEdge[];
}) {
  const { t } = useI18n();

  // Comments grouped by their post_id, each list kept in arrival order.
  const commentsByPost = useMemo(() => {
    const m = new Map<number, ForumComment[]>();
    for (const c of comments) {
      const arr = m.get(c.post_id);
      if (arr) arr.push(c);
      else m.set(c.post_id, [c]);
    }
    return m;
  }, [comments]);

  // Set of agents that are followed by someone (the target side of any edge),
  // used to mark a post author as "followed".
  const followedTargets = useMemo(
    () => new Set(follows.map((f) => f.target_id)),
    [follows],
  );

  // Newest tick first; stable for equal ticks by post_id descending.
  const ordered = useMemo(
    () => [...posts].sort((a, b) => (b.tick - a.tick) || (b.post_id - a.post_id)),
    [posts],
  );

  if (ordered.length === 0) {
    return (
      <div className="card p-4">
        <div className="text-center py-10 text-surface-400 text-sm">{t('forum.empty')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-3 max-w-2xl">
      {ordered.map((post) => {
        const postComments = commentsByPost.get(post.post_id) ?? [];
        const followed = followedTargets.has(post.author_id);
        return (
          <div key={post.post_id} className="card p-4">
            {/* Author header */}
            <div className="flex items-center gap-2">
              <span
                className="w-8 h-8 rounded-md shrink-0"
                style={{ background: agentColor(post.author_id) }}
                aria-hidden
              />
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-semibold text-surface-900 dark:text-white">
                    A{post.author_id}
                  </span>
                  {followed && (
                    <span className="badge bg-primary-100 text-primary-700 dark:bg-primary-500/15 dark:text-primary-300">
                      {t('forum.followed')}
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-surface-400">{t('forum.tick', { tick: post.tick })}</div>
              </div>
            </div>

            {/* Body */}
            <p className="mt-2 text-sm text-surface-800 dark:text-surface-200 whitespace-pre-wrap">
              {post.content}
            </p>

            {/* Nested comments */}
            <div className="mt-3 pl-4 border-l-2 border-surface-100 dark:border-surface-700 space-y-2">
              <div className="text-[10px] uppercase tracking-wide text-surface-400">
                {postComments.length > 0
                  ? t('forum.commentsCount', { count: postComments.length })
                  : t('forum.noComments')}
              </div>
              {postComments.map((c) => (
                <div key={c.comment_id} className="flex items-start gap-2">
                  <span
                    className="w-5 h-5 rounded shrink-0 mt-0.5"
                    style={{ background: agentColor(c.author_id) }}
                    aria-hidden
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-[10px] text-surface-400">
                      <span className="font-mono font-semibold text-surface-600 dark:text-surface-300">
                        A{c.author_id}
                      </span>
                      <span>{t('forum.tick', { tick: c.tick })}</span>
                    </div>
                    <p className="text-xs text-surface-700 dark:text-surface-300 whitespace-pre-wrap">
                      {c.content}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Social tab — lightweight self-drawn SVG follow graph. Nodes are agents that
// participate (posted / followed / were followed); directed edges are follows
// (agent_id → target_id, arrow points at the followed agent). Nodes are laid
// out on a circle; node size scales with in-degree (follower count).
// ─────────────────────────────────────────────────────────────────────────

function SocialTab({ posts, follows }: { posts: ForumPost[]; follows: FollowEdge[] }) {
  const { t } = useI18n();

  const graph = useMemo(() => {
    // Collect participating agents and per-agent stats.
    const ids = new Set<number>();
    const inDeg = new Map<number, number>();   // followers
    const outDeg = new Map<number, number>();  // following
    const postCount = new Map<number, number>();

    for (const p of posts) {
      ids.add(p.author_id);
      postCount.set(p.author_id, (postCount.get(p.author_id) ?? 0) + 1);
    }
    // De-dup edges so repeated follow events don't draw / count twice.
    const seenEdges = new Set<string>();
    const edges: FollowEdge[] = [];
    for (const f of follows) {
      ids.add(f.agent_id);
      ids.add(f.target_id);
      const key = `${f.agent_id}->${f.target_id}`;
      if (seenEdges.has(key)) continue;
      seenEdges.add(key);
      edges.push(f);
      inDeg.set(f.target_id, (inDeg.get(f.target_id) ?? 0) + 1);
      outDeg.set(f.agent_id, (outDeg.get(f.agent_id) ?? 0) + 1);
    }

    const nodeIds = [...ids].sort((a, b) => a - b);
    return { nodeIds, edges, inDeg, outDeg, postCount };
  }, [posts, follows]);

  const [hovered, setHovered] = useState<number | null>(null);

  if (graph.nodeIds.length === 0) {
    return (
      <div className="card p-4">
        <div className="text-center py-10 text-surface-400 text-sm">{t('social.empty')}</div>
      </div>
    );
  }

  // Circular layout.
  const W = 720;
  const H = 520;
  const cx = W / 2;
  const cy = H / 2;
  const radius = Math.min(W, H) / 2 - 70;
  const n = graph.nodeIds.length;

  const pos = new Map<number, { x: number; y: number }>();
  graph.nodeIds.forEach((id, i) => {
    // Single node sits in the center; otherwise spread around the circle.
    if (n === 1) {
      pos.set(id, { x: cx, y: cy });
    } else {
      const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
      pos.set(id, { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) });
    }
  });

  const maxIn = Math.max(1, ...graph.nodeIds.map((id) => graph.inDeg.get(id) ?? 0));
  const nodeRadius = (id: number) => 12 + ((graph.inDeg.get(id) ?? 0) / maxIn) * 14;

  // Whether an edge touches the hovered node (for highlighting).
  const edgeActive = (e: FollowEdge) =>
    hovered === null || e.agent_id === hovered || e.target_id === hovered;
  const nodeActive = (id: number) => {
    if (hovered === null) return true;
    if (id === hovered) return true;
    return graph.edges.some(
      (e) =>
        (e.agent_id === hovered && e.target_id === id) ||
        (e.target_id === hovered && e.agent_id === id),
    );
  };

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300">
          {t('social.title')}
        </h3>
        <div className="text-[10px] text-surface-400 space-x-3">
          <span>{t('social.legend.node')}</span>
          <span>{t('social.legend.edge')}</span>
        </div>
      </div>

      <div className="w-full overflow-x-auto">
        <svg
          width="100%"
          viewBox={`0 0 ${W} ${H}`}
          className="min-w-[480px]"
          role="img"
          aria-label={t('social.title')}
        >
          <defs>
            <marker
              id="arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
            </marker>
            <marker
              id="arrow-hi"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#0d9488" />
            </marker>
          </defs>

          {/* Edges: shorten the segment so the arrowhead lands at the node rim. */}
          {graph.edges.map((e) => {
            const a = pos.get(e.agent_id)!;
            const b = pos.get(e.target_id)!;
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const len = Math.hypot(dx, dy) || 1;
            const ux = dx / len;
            const uy = dy / len;
            const rA = nodeRadius(e.agent_id);
            const rB = nodeRadius(e.target_id);
            const x1 = a.x + ux * rA;
            const y1 = a.y + uy * rA;
            const x2 = b.x - ux * (rB + 6);
            const y2 = b.y - uy * (rB + 6);
            const active = edgeActive(e);
            return (
              <line
                key={`${e.agent_id}->${e.target_id}`}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={active ? '#0d9488' : '#cbd5e1'}
                strokeWidth={active && hovered !== null ? 2 : 1.25}
                opacity={active ? 0.9 : 0.25}
                markerEnd={active && hovered !== null ? 'url(#arrow-hi)' : 'url(#arrow)'}
              />
            );
          })}

          {/* Nodes */}
          {graph.nodeIds.map((id) => {
            const p = pos.get(id)!;
            const r = nodeRadius(id);
            const active = nodeActive(id);
            return (
              <g
                key={id}
                transform={`translate(${p.x}, ${p.y})`}
                opacity={active ? 1 : 0.3}
                onMouseEnter={() => setHovered(id)}
                onMouseLeave={() => setHovered(null)}
                style={{ cursor: 'pointer' }}
              >
                <circle
                  r={r}
                  fill={agentColor(id)}
                  stroke={hovered === id ? '#0d9488' : '#ffffff'}
                  strokeWidth={hovered === id ? 3 : 1.5}
                />
                <text
                  textAnchor="middle"
                  dy={r + 12}
                  className="fill-surface-600 dark:fill-surface-300"
                  style={{ fontSize: 11, fontFamily: 'monospace' }}
                >
                  A{id}
                </text>
                <title>
                  {`A${id} · ${t('social.followers', { count: graph.inDeg.get(id) ?? 0 })} · ${t('social.following', { count: graph.outDeg.get(id) ?? 0 })} · ${t('social.posts', { count: graph.postCount.get(id) ?? 0 })}`}
                </title>
              </g>
            );
          })}
        </svg>
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
