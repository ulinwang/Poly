import { useParams } from 'react-router-dom';
import { useEffect, useState } from 'react';
import {
  Play, Users, Clock, ArrowLeft, ExternalLink, FlaskConical,
  CalendarDays, BarChart3, CheckCircle2, XCircle, Loader2, Layers,
} from 'lucide-react';
import { api } from '../lib/api';
import { useMarketStore, useExperimentStore, useSettingsStore } from '../stores';
import type { MarketDetail as MarketDetailType, Experiment, Market } from '../types';

const statusStyle: Record<string, string> = {
  running: 'bg-success/15 text-success',
  completed: 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300',
  cancelled: 'bg-warning/15 text-warning',
  error: 'bg-danger/15 text-danger',
  queued: 'bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300',
};

function formatVol(v: number) {
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}k`;
  return `$${v.toFixed(0)}`;
}

// Deterministic hash for the placeholder multi-outcome chart heights.
function hashSlug(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return h;
}

function formatDate(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export default function MarketDetail() {
  const { slug } = useParams<{ slug: string }>();
  const [market, setMarket] = useState<MarketDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  // Sibling sub-markets when this market belongs to a multi-market event.
  const [siblings, setSiblings] = useState<Market[]>([]);
  const [nAgents, setNAgents] = useState(20);
  const [nTicks, setNTicks] = useState(12);
  const [personaSet, setPersonaSet] = useState<'archetype' | 'calibrated' | 'no_signal'>('archetype');
  const [starting, setStarting] = useState(false);

  const selectMarket = useMarketStore((s) => s.selectMarket);
  const setActiveId = useExperimentStore((s) => s.setActiveId);
  const apiSettings = useSettingsStore((s) => s.apiSettings);

  useEffect(() => {
    if (!slug) return;
    selectMarket(slug);
    setLoading(true);
    setSiblings([]);
    api.getMarket(slug)
      .then((res) => {
        setMarket(res.market);
        // If this market is part of a multi-market event, load its siblings so
        // the user can switch between outcomes. Single-market events return one
        // entry, which we treat as "no siblings".
        const ev = res.market.event_slug;
        if (ev) {
          api.getEventMarkets(ev)
            .then((r) => setSiblings(r.markets.length > 1 ? r.markets : []))
            .catch((err) => console.error('Failed to load event outcomes:', err));
        }
      })
      .catch((err) => console.error('Failed to load market:', err))
      .finally(() => setLoading(false));
    api.listExperiments({ slug, limit: 50 })
      .then((res) => setExperiments(res.experiments))
      .catch((err) => console.error('Failed to load market experiments:', err));
  }, [slug, selectMarket]);

  const handleStart = async () => {
    if (!slug) return;
    setStarting(true);
    try {
      const res = await api.createExperiment({
        slug,
        n_agents: nAgents,
        n_ticks: nTicks,
        persona_set: personaSet,
      });
      setActiveId(res.run_id);
      window.location.hash = `#/experiments/${res.run_id}`;
    } catch (err) {
      console.error('Failed to start experiment:', err);
      alert('Failed to start experiment: ' + (err as Error).message);
    } finally {
      setStarting(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto py-20 flex justify-center text-surface-400">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }
  if (!market) {
    return <div className="text-center py-20 text-surface-400">Market not found</div>;
  }

  const polymarketUrl = market.event_slug
    ? `https://polymarket.com/event/${market.event_slug}`
    : null;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Back link */}
      <a href="#/markets" className="inline-flex items-center gap-1 text-sm text-surface-500 hover:text-surface-700 dark:hover:text-surface-300">
        <ArrowLeft className="w-4 h-4" />
        返回市场列表
      </a>

      {/* Market header */}
      <div className="card p-6">
        <div className="flex items-start gap-4">
          {market.icon_url ? (
            <img
              src={market.icon_url}
              alt=""
              className="w-14 h-14 rounded-xl object-cover flex-shrink-0 bg-surface-100 dark:bg-surface-700"
            />
          ) : (
            <div className={`w-14 h-14 rounded-xl flex items-center justify-center text-2xl flex-shrink-0 ${
              market.is_live ? 'bg-primary-50 dark:bg-primary-900/30' : 'bg-surface-100 dark:bg-surface-700'
            }`}>
              {market.is_live ? '🟢' : '🔴'}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-bold text-surface-900 dark:text-white leading-snug">
              {market.question || market.slug}
            </h1>
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <span className={`badge ${market.is_live ? 'badge-live' : 'badge-resolved'}`}>
                {market.is_live ? 'Open' : 'Resolved'}
              </span>
              <span className="inline-flex items-center gap-1 text-xs text-surface-500">
                <BarChart3 className="w-3.5 h-3.5" /> {formatVol(market.volume)} Vol
              </span>
              <span className="inline-flex items-center gap-1 text-xs text-surface-500">
                <CalendarDays className="w-3.5 h-3.5" /> 截止 {formatDate(market.end_date_iso)}
              </span>
            </div>
          </div>
          {polymarketUrl && (
            <a
              href={polymarketUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary flex items-center gap-1.5 flex-shrink-0 text-sm"
            >
              <ExternalLink className="w-4 h-4" />
              在 Polymarket 查看
            </a>
          )}
        </div>

        {/* Description */}
        {market.description && (
          <p className="mt-4 text-sm text-surface-600 dark:text-surface-400 leading-relaxed line-clamp-4">
            {market.description}
          </p>
        )}

        {/* Params */}
        <div className="mt-4 flex flex-wrap gap-2">
          {market.categories?.slice(0, 4).map((c) => (
            <span key={c} className="badge bg-surface-100 dark:bg-surface-700 text-surface-600 dark:text-surface-300">
              {c}
            </span>
          ))}
          <span className="badge bg-surface-100 dark:bg-surface-700 text-surface-500">tick {market.tick_size}</span>
          <span className="badge bg-surface-100 dark:bg-surface-700 text-surface-500">fee {(market.taker_fee_bps / 100).toFixed(2)}%</span>
          <span className="badge bg-surface-100 dark:bg-surface-700 text-surface-500 font-mono text-[10px]">
            {market.condition_id.slice(0, 10)}…
          </span>
        </div>
      </div>

      {/* Sibling outcomes (multi-market event). Each links to its own detail
          page; the simulation always targets the single selected sub-market. */}
      {siblings.length > 1 && (
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-2">
            <Layers className="w-4 h-4 text-primary-500" />
            <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300">
              该事件的其它结果
            </h3>
            <span className="text-xs text-surface-400">({siblings.length})</span>
          </div>
          <p className="text-xs text-surface-400 mb-4">
            这是一个多结果事件。仿真针对当前选中的单个结果子市场，点击下方结果可切换。
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {siblings.map((s) => {
              const active = s.slug === market.slug;
              return (
                <a
                  key={s.slug}
                  href={`#/markets/${s.slug}`}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${
                    active
                      ? 'border-primary-400 bg-primary-50 dark:bg-primary-900/20 dark:border-primary-600'
                      : 'border-surface-200 dark:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-700/50'
                  }`}
                >
                  <span className="text-sm text-surface-700 dark:text-surface-200 truncate flex-1">
                    {s.group_title || s.question || s.slug}
                  </span>
                  {active && (
                    <span className="badge text-[10px] bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300 flex-shrink-0">
                      当前
                    </span>
                  )}
                  <span className="text-xs text-surface-400 flex-shrink-0">{formatVol(s.volume)}</span>
                </a>
              );
            })}
          </div>
          {/* Simplified multi-line placeholder — real multi-outcome pricing not wired. */}
          <div className="mt-4 h-12 flex items-end gap-[3px]" aria-hidden="true">
            {siblings.slice(0, 24).map((s) => (
              <div
                key={s.slug}
                className="flex-1 rounded-sm bg-primary-200/70 dark:bg-primary-800/40"
                style={{ height: `${20 + (Math.abs(hashSlug(s.slug)) % 70)}%` }}
              />
            ))}
          </div>
        </div>
      )}

      {/* This market's experiments */}
      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <FlaskConical className="w-4 h-4 text-surface-500" />
          <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300">
            该市场的实验
          </h3>
          <span className="text-xs text-surface-400">({experiments.length})</span>
        </div>
        {experiments.length === 0 ? (
          <p className="text-sm text-surface-400 py-2">还没有针对该市场的实验，在下方新建一个。</p>
        ) : (
          <div className="space-y-1.5 max-h-72 overflow-y-auto">
            {experiments.map((exp) => (
              <a
                key={exp.id}
                href={`#/experiments/${exp.id}`}
                className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-surface-50 dark:hover:bg-surface-700/50 transition-colors"
              >
                {exp.status === 'running'
                  ? <Loader2 className="w-4 h-4 text-success animate-spin flex-shrink-0" />
                  : exp.status === 'completed'
                    ? <CheckCircle2 className="w-4 h-4 text-primary-500 flex-shrink-0" />
                    : <XCircle className="w-4 h-4 text-surface-400 flex-shrink-0" />}
                <span className="text-sm text-surface-700 dark:text-surface-300 font-mono">{exp.id.slice(0, 8)}</span>
                <span className="text-xs text-surface-400">{exp.n_agents} agents · {exp.n_ticks} ticks · {exp.persona_set}</span>
                <span className={`badge text-[10px] ml-auto ${statusStyle[exp.status] || ''}`}>{exp.status}</span>
              </a>
            ))}
          </div>
        )}
      </div>

      {/* New experiment */}
      <div className="card p-6">
        <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-4">
          新建实验
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs text-surface-500 mb-1">
              <Users className="w-3 h-3 inline mr-1" />
              Agent 数量 ({nAgents})
            </label>
            <input type="range" min="3" max="100" value={nAgents}
              onChange={(e) => setNAgents(Number(e.target.value))} className="w-full" />
          </div>
          <div>
            <label className="block text-xs text-surface-500 mb-1">
              <Clock className="w-3 h-3 inline mr-1" />
              Tick 数 ({nTicks})
            </label>
            <input type="range" min="1" max="48" value={nTicks}
              onChange={(e) => setNTicks(Number(e.target.value))} className="w-full" />
          </div>
          <div>
            <label className="block text-xs text-surface-500 mb-1">Persona 组</label>
            <select value={personaSet}
              onChange={(e) => setPersonaSet(e.target.value as 'archetype' | 'calibrated' | 'no_signal')}
              className="input">
              <option value="archetype">Archetype (K-means)</option>
              <option value="calibrated">Calibrated (Real wallets)</option>
              <option value="no_signal">No Signal (Ablation)</option>
            </select>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3 flex-wrap">
          <button onClick={handleStart} disabled={starting || !market.is_live}
            className="btn-primary flex items-center gap-2">
            <Play className="w-4 h-4" />
            {starting ? '启动中…' : '开始仿真'}
          </button>
          {!market.is_live && (
            <span className="text-sm text-warning">该市场已结算，无法仿真。</span>
          )}
          <span className="text-xs text-surface-400 ml-auto">
            LLM: {apiSettings.provider} / {apiSettings.model}
          </span>
        </div>
      </div>
    </div>
  );
}
