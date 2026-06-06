import { useParams } from 'react-router-dom';
import { useEffect, useState } from 'react';
import {
  Play, Users, Clock, ArrowLeft, ExternalLink, FlaskConical,
  CalendarDays, BarChart3, CheckCircle2, XCircle, Loader2, Layers,
} from 'lucide-react';
import { api } from '../lib/api';
import { useMarketStore, useExperimentStore, useSettingsStore } from '../stores';
import { useI18n } from '../lib/i18n';
import type { MarketDetail as MarketDetailType, Experiment, Market, ApiKey } from '../types';

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

function formatDate(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export default function MarketDetail() {
  const { t } = useI18n();
  const { slug } = useParams<{ slug: string }>();
  const [market, setMarket] = useState<MarketDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  // Sibling sub-markets when this market belongs to a multi-market event.
  const [siblings, setSiblings] = useState<Market[]>([]);
  const [nAgents, setNAgents] = useState(20);
  const [nTicks, setNTicks] = useState(12);
  const [seed, setSeed] = useState(0);
  const [personaSet, setPersonaSet] = useState<'archetype' | 'calibrated' | 'no_signal'>('archetype');
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  // Empty string = use the default API settings (no api_key_id sent).
  const [apiKeyId, setApiKeyId] = useState('');
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
    api.listApiKeys()
      .then((res) => setApiKeys(res.keys))
      .catch((err) => console.error('Failed to load API keys:', err));
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
        seed,
        // Only send api_key_id when a stored key is chosen; otherwise the
        // backend falls back to the default API settings.
        ...(apiKeyId ? { api_key_id: Number(apiKeyId) } : {}),
      });
      setActiveId(res.run_id);
      window.location.hash = `#/experiments/${res.run_id}`;
    } catch (err) {
      console.error('Failed to start experiment:', err);
      alert(t('detail.startFailed', { msg: (err as Error).message }));
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
    return <div className="text-center py-20 text-surface-400">{t('detail.notFound')}</div>;
  }

  const polymarketUrl = market.event_slug
    ? `https://polymarket.com/event/${market.event_slug}`
    : null;

  // For a multi-market event, the left header shows the EVENT's title / image /
  // description by default; the individual sub-market's title & image appear in
  // the outcomes list below (the selected one highlighted). Single-market
  // events fall back to the market's own fields.
  const isMultiEvent = siblings.length > 1;
  const headerTitle = (isMultiEvent && market.event_title) || market.question || market.slug;
  const headerImage = (isMultiEvent && market.event_icon) ? market.event_icon : market.icon_url;
  const headerDesc = (isMultiEvent && market.event_description) ? market.event_description : market.description;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Back link */}
      <a href="#/markets" className="inline-flex items-center gap-1 text-sm text-surface-500 hover:text-surface-700 dark:hover:text-surface-300">
        <ArrowLeft className="w-4 h-4" />
        {t('detail.back')}
      </a>

      {/* Two-column layout: market info (left) · experiments + new run (right) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
      {/* Left column: market */}
      <div className="space-y-6">

      {/* Market header */}
      <div className="card p-6">
        <div className="flex items-start gap-4">
          {headerImage ? (
            <img
              src={headerImage}
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
              {headerTitle}
            </h1>
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <span className={`badge ${market.is_live ? 'badge-live' : 'badge-resolved'}`}>
                {market.is_live ? t('market.open') : t('market.resolved')}
              </span>
              <span className="inline-flex items-center gap-1 text-xs text-surface-500">
                <BarChart3 className="w-3.5 h-3.5" /> {formatVol(market.volume)} {t('market.vol')}
              </span>
              <span className="inline-flex items-center gap-1 text-xs text-surface-500">
                <CalendarDays className="w-3.5 h-3.5" /> {t('detail.deadline', { date: formatDate(market.end_date_iso) })}
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
              {t('detail.viewOnPolymarket')}
            </a>
          )}
        </div>

        {/* Description (event-level for multi-market events) */}
        {headerDesc && (
          <p className="mt-4 text-sm text-surface-600 dark:text-surface-400 leading-relaxed line-clamp-4">
            {headerDesc}
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
              {t('detail.otherOutcomes')}
            </h3>
            <span className="text-xs text-surface-400">({siblings.length})</span>
          </div>
          <p className="text-xs text-surface-400 mb-4">
            {t('detail.multiOutcomeHint')}
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
                  {s.icon_url && (
                    <img
                      src={s.icon_url}
                      alt=""
                      className="w-6 h-6 rounded object-cover flex-shrink-0 bg-surface-100 dark:bg-surface-700"
                    />
                  )}
                  <span className="text-sm text-surface-700 dark:text-surface-200 truncate flex-1">
                    {s.group_title || s.question || s.slug}
                  </span>
                  {active && (
                    <span className="badge text-[10px] bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300 flex-shrink-0">
                      {t('common.current')}
                    </span>
                  )}
                  <span className="text-xs text-surface-400 flex-shrink-0">{formatVol(s.volume)}</span>
                </a>
              );
            })}
          </div>
          {/* Per-outcome YES probability bars (real Polymarket quotes). Bar
              height reflects each outcome's YES price; outcomes without a live
              quote render as a flat grey "暂无行情" bar. */}
          <div className="mt-4 flex items-end gap-[3px] h-16">
            {siblings.slice(0, 24).map((s) => {
              const yes = s.yes_price;
              const hasPrice = yes != null && Number.isFinite(yes);
              const heightPct = hasPrice ? Math.max(4, Math.round(yes! * 100)) : 100;
              const cents = hasPrice ? Math.round(yes! * 100) : null;
              return (
                <div
                  key={s.slug}
                  className="flex-1 h-full flex items-end"
                  title={hasPrice
                    ? `${s.group_title || s.slug}: ${cents}¢`
                    : `${s.group_title || s.slug}: ${t('detail.noQuote')}`}
                >
                  <div
                    className={`w-full rounded-sm ${
                      hasPrice
                        ? 'bg-primary-400/80 dark:bg-primary-500/60'
                        : 'bg-surface-200 dark:bg-surface-600'
                    }`}
                    style={{ height: `${heightPct}%` }}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}

      </div>{/* end left column */}

      {/* Right column: experiments + new experiment */}
      <div className="space-y-6">

      {/* This market's experiments */}
      <div className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <FlaskConical className="w-4 h-4 text-surface-500" />
          <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300">
            {t('detail.marketExperiments')}
          </h3>
          <span className="text-xs text-surface-400">({experiments.length})</span>
        </div>
        {experiments.length === 0 ? (
          <p className="text-sm text-surface-400 py-2">{t('detail.noExperiments')}</p>
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
                <span className="text-xs text-surface-400">
                  {exp.n_agents} {t('detail.unitAgents')} · {exp.n_ticks} {t('detail.unitTicks')} · {exp.persona_set}
                  {exp.seed != null ? ` · ${t('detail.seedLabel', { seed: exp.seed })}` : ''}
                </span>
                <span className={`badge text-[10px] ml-auto ${statusStyle[exp.status] || ''}`}>{exp.status}</span>
              </a>
            ))}
          </div>
        )}
      </div>

      {/* New experiment */}
      <div className="card p-6">
        <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-4">
          {t('detail.newExperiment')}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-surface-500 mb-1">
              <Users className="w-3 h-3 inline mr-1" />
              {t('detail.agentCount', { count: nAgents })}
            </label>
            <input type="range" min="3" max="100" value={nAgents}
              onChange={(e) => setNAgents(Number(e.target.value))} className="w-full" />
          </div>
          <div>
            <label className="block text-xs text-surface-500 mb-1">
              <Clock className="w-3 h-3 inline mr-1" />
              {t('detail.tickCount', { count: nTicks })}
            </label>
            <input type="range" min="1" max="48" value={nTicks}
              onChange={(e) => setNTicks(Number(e.target.value))} className="w-full" />
          </div>
          <div>
            <label className="block text-xs text-surface-500 mb-1">{t('detail.personaSet')}</label>
            <select value={personaSet}
              onChange={(e) => setPersonaSet(e.target.value as 'archetype' | 'calibrated' | 'no_signal')}
              className="input">
              <option value="archetype">{t('detail.persona.archetype')}</option>
              <option value="calibrated">{t('detail.persona.calibrated')}</option>
              <option value="no_signal">{t('detail.persona.noSignal')}</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-surface-500 mb-1">
              {t('detail.seed')}
            </label>
            <input type="number" min="0" step="1" value={seed}
              onChange={(e) => setSeed(Number.isFinite(e.target.valueAsNumber) ? Math.trunc(e.target.valueAsNumber) : 0)}
              className="input" />
            <p className="mt-1 text-[10px] text-surface-400">{t('detail.seedHint')}</p>
          </div>
          <div>
            <label className="block text-xs text-surface-500 mb-1">{t('detail.apiKey')}</label>
            <select value={apiKeyId}
              onChange={(e) => setApiKeyId(e.target.value)}
              className="input">
              <option value="">{t('detail.useDefaultSettings')}</option>
              {apiKeys.map((k) => (
                <option key={k.id} value={String(k.id)}>
                  {k.name} ({k.provider})
                </option>
              ))}
            </select>
            <p className="mt-1 text-[10px] text-surface-400">
              {t('detail.apiKeyHint')}
            </p>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3 flex-wrap">
          <button onClick={handleStart} disabled={starting || !market.is_live}
            className="btn-primary flex items-center gap-2">
            <Play className="w-4 h-4" />
            {starting ? t('detail.starting') : t('detail.startSimulation')}
          </button>
          {!market.is_live && (
            <span className="text-sm text-warning">{t('detail.resolvedNoSim')}</span>
          )}
          <span className="text-xs text-surface-400 ml-auto">
            LLM: {apiSettings.provider} / {apiSettings.model}
          </span>
        </div>
      </div>

      </div>{/* end right column */}
      </div>{/* end two-column grid */}
    </div>
  );
}
