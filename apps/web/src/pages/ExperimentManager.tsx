import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  FlaskConical, Clock, CheckCircle, XCircle, AlertCircle,
  RefreshCw, Search, ChevronLeft, ChevronRight, Filter, ArrowLeft, LayoutGrid,
} from 'lucide-react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { api } from '../lib/api';
import { useI18n } from '../lib/i18n';
import type { Experiment } from '../types';

const statusIcons: Record<string, React.ReactNode> = {
  running: <Clock className="w-4 h-4 text-success animate-pulse" />,
  completed: <CheckCircle className="w-4 h-4 text-primary-500" />,
  cancelled: <XCircle className="w-4 h-4 text-warning" />,
  error: <AlertCircle className="w-4 h-4 text-danger" />,
  queued: <Clock className="w-4 h-4 text-surface-400" />,
};

const statusColors: Record<string, string> = {
  running: 'text-success bg-success/10',
  completed: 'text-primary-600 bg-primary-50 dark:bg-primary-900/20',
  cancelled: 'text-warning bg-warning/10',
  error: 'text-danger bg-danger/10',
  queued: 'text-surface-500 bg-surface-100 dark:bg-surface-800',
};

// Order in which status badges appear on the market grid cards.
const STATUS_ORDER = ['running', 'completed', 'cancelled', 'error', 'queued'];

const PAGE_SIZE = 20;
// Large page used by the grid view so we can aggregate every experiment client-side.
const AGGREGATE_LIMIT = 1000;

interface MarketGroup {
  slug: string;
  question?: string;
  total: number;
  statusCounts: Record<string, number>;
}

export default function ExperimentManager() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedSlug = searchParams.get('slug') || '';

  return selectedSlug ? (
    <MarketExperimentList
      slug={selectedSlug}
      onBack={() => setSearchParams({})}
    />
  ) : (
    <MarketGrid
      onSelect={(slug) => setSearchParams({ slug })}
    />
  );
}

// ---------------------------------------------------------------------------
// Grid view: one card per market (slug), aggregated from all experiments.
// ---------------------------------------------------------------------------
function MarketGrid({ onSelect }: { onSelect: (slug: string) => void }) {
  const { t } = useI18n();
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [questions, setQuestions] = useState<Record<string, string>>({});
  const [statusFilter, setStatusFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listExperiments({ limit: AGGREGATE_LIMIT });
      setExperiments(res.experiments);
    } catch (err) {
      setError(t('exp.loadFailed', { msg: (err as Error).message }));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  // Best-effort: map slug -> market question for nicer titles. Failure is non-fatal.
  useEffect(() => {
    api.listMarkets({ limit: 200 })
      .then((res) => {
        const map: Record<string, string> = {};
        for (const m of res.markets) map[m.slug] = m.question;
        setQuestions(map);
      })
      .catch(() => { /* fall back to slug-only titles */ });
  }, []);

  // Group experiments by slug, applying status filter to the membership counts.
  const groups = useMemo<MarketGroup[]>(() => {
    const bySlug = new Map<string, MarketGroup>();
    for (const exp of experiments) {
      if (statusFilter && exp.status !== statusFilter) continue;
      let g = bySlug.get(exp.slug);
      if (!g) {
        g = { slug: exp.slug, question: questions[exp.slug], total: 0, statusCounts: {} };
        bySlug.set(exp.slug, g);
      }
      g.total += 1;
      g.statusCounts[exp.status] = (g.statusCounts[exp.status] || 0) + 1;
    }
    let list = Array.from(bySlug.values());
    const q = searchQuery.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (g) =>
          g.slug.toLowerCase().includes(q) ||
          (g.question?.toLowerCase().includes(q) ?? false),
      );
    }
    list.sort((a, b) => b.total - a.total || a.slug.localeCompare(b.slug));
    return list;
  }, [experiments, questions, statusFilter, searchQuery]);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FlaskConical className="w-5 h-5 text-primary-600" />
          <h1 className="text-2xl font-semibold tracking-tight text-surface-900 dark:text-white">{t('exp.title')}</h1>
          <span className="text-sm text-surface-400">({t('exp.marketCount', { count: groups.length })})</span>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="p-2 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
          title={t('common.refresh')}
        >
          <RefreshCw className={`w-4 h-4 text-surface-500 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('exp.searchPlaceholder')}
            className="input pl-9 w-full"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-surface-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="input py-2"
          >
            <option value="">{t('exp.allStatus')}</option>
            <option value="running">{t('exp.status.running')}</option>
            <option value="completed">{t('exp.status.completed')}</option>
            <option value="cancelled">{t('exp.status.cancelled')}</option>
            <option value="error">{t('exp.status.error')}</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="card p-4 bg-danger/10 border-danger/20 text-danger text-sm">
          {error}
        </div>
      )}

      {/* Grid */}
      {groups.length === 0 ? (
        <div className="card p-12 text-center">
          <FlaskConical className="w-12 h-12 text-surface-300 mx-auto mb-3" />
          <p className="text-surface-500 dark:text-surface-400">
            {searchQuery || statusFilter ? t('exp.noMatchingMarkets') : t('exp.noExperimentsYet')}
          </p>
          <p className="text-sm text-surface-400 mt-1">
            {t('exp.selectMarketHint')}
          </p>
        </div>
      ) : (
        <VirtualExperimentGrid groups={groups} onSelect={onSelect} statusColors={statusColors} statusIcons={statusIcons} />
      )}
    </div>
  );
}

// Responsive virtualized grid for experiment market cards. Only renders the
// rows that are actually in the viewport; column count follows the container
// width (md=2, xl=3).
function VirtualExperimentGrid({
  groups,
  onSelect,
  statusColors,
  statusIcons,
}: {
  groups: MarketGroup[];
  onSelect: (slug: string) => void;
  statusColors: Record<string, string>;
  statusIcons: Record<string, React.ReactNode>;
}) {
  const { t } = useI18n();
  const parentRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = parentRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const cols = width >= 1280 ? 3 : width >= 768 ? 2 : 1;
  const rows = Math.ceil(groups.length / cols);

  const virtualizer = useVirtualizer({
    count: rows,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 140,
    overscan: 3,
  });

  return (
    <div
      ref={parentRef}
      className="h-[calc(100vh-280px)] overflow-y-auto scrollbar-hide"
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const start = virtualRow.index * cols;
          const rowGroups = groups.slice(start, start + cols);
          return (
            <div
              key={virtualRow.key}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              className="absolute top-0 left-0 w-full"
              style={{ transform: `translateY(${virtualRow.start}px)` }}
            >
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                {rowGroups.map((g) => (
                  <button
                    key={g.slug}
                    onClick={() => onSelect(g.slug)}
                    className="card card-hover p-4 text-left flex flex-col gap-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-medium text-surface-800 dark:text-surface-100 line-clamp-2">
                        {g.question || g.slug}
                      </span>
                      <span className="badge text-[10px] bg-surface-100 dark:bg-surface-800 text-surface-500 flex-shrink-0">
                        {g.total === 1 ? t('exp.runsOne', { count: g.total }) : t('exp.runsMany', { count: g.total })}
                      </span>
                    </div>
                    {g.question && (
                      <div className="text-xs text-surface-400 truncate -mt-1">{g.slug}</div>
                    )}
                    <div className="flex flex-wrap gap-1.5">
                      {STATUS_ORDER.filter((s) => g.statusCounts[s]).map((s) => (
                        <span
                          key={s}
                          className={`badge text-[10px] inline-flex items-center gap-1 ${statusColors[s] || ''}`}
                        >
                          {statusIcons[s]}
                          {g.statusCounts[s]} {t(`exp.status.${s}`)}
                        </span>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// List view: experiments for a single market (slug), paginated server-side.
// ---------------------------------------------------------------------------
function MarketExperimentList({ slug, onBack }: { slug: string; onBack: () => void }) {
  const { t } = useI18n();
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');
  const [question, setQuestion] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset paging whenever the market changes.
  useEffect(() => {
    setOffset(0);
    setStatusFilter('');
  }, [slug]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listExperiments({
        slug,
        status: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setExperiments(res.experiments);
      setTotal(res.total);
    } catch (err) {
      setError(t('exp.loadFailed', { msg: (err as Error).message }));
    } finally {
      setLoading(false);
    }
  }, [slug, statusFilter, offset, t]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    let active = true;
    api.getMarket(slug)
      .then((res) => { if (active) setQuestion(res.market.question); })
      .catch(() => { /* fall back to slug-only title */ });
    return () => { active = false; };
  }, [slug]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Back link */}
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm text-surface-500 hover:text-primary-600 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        <LayoutGrid className="w-4 h-4" />
        {t('exp.allMarkets')}
      </button>

      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-primary-600 flex-shrink-0" />
            <h1 className="text-xl font-bold text-surface-900 dark:text-white truncate">
              {question || slug}
            </h1>
            <span className="text-sm text-surface-400 flex-shrink-0">({total})</span>
          </div>
          {question && <div className="text-xs text-surface-400 mt-0.5 truncate">{slug}</div>}
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="p-2 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors flex-shrink-0"
          title={t('common.refresh')}
        >
          <RefreshCw className={`w-4 h-4 text-surface-500 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Status filter */}
      <div className="flex items-center gap-2">
        <Filter className="w-4 h-4 text-surface-400" />
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
          className="input py-2"
        >
          <option value="">{t('exp.allStatus')}</option>
          <option value="running">{t('exp.status.running')}</option>
          <option value="completed">{t('exp.status.completed')}</option>
          <option value="cancelled">{t('exp.status.cancelled')}</option>
          <option value="error">{t('exp.status.error')}</option>
        </select>
      </div>

      {error && (
        <div className="card p-4 bg-danger/10 border-danger/20 text-danger text-sm">
          {error}
        </div>
      )}

      {/* List */}
      {experiments.length === 0 ? (
        <div className="card p-12 text-center">
          <FlaskConical className="w-12 h-12 text-surface-300 mx-auto mb-3" />
          <p className="text-surface-500 dark:text-surface-400">
            {statusFilter ? t('exp.noMatchingExperiments') : t('exp.noExperimentsForMarket')}
          </p>
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {experiments.map((exp) => (
              <a
                key={exp.id}
                href={`#/experiments/${exp.id}`}
                className="card p-4 flex items-center gap-4 hover:shadow-md transition-shadow"
              >
                <div className="flex-shrink-0">
                  {statusIcons[exp.status] || statusIcons.queued}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-surface-800 dark:text-surface-100 truncate">
                      {exp.slug}
                    </span>
                    <span className={`badge text-[10px] ${statusColors[exp.status] || ''}`}>
                      {t(`exp.status.${exp.status}`)}
                    </span>
                  </div>
                  <div className="text-xs text-surface-400 mt-0.5">
                    {exp.n_agents} {t('detail.unitAgents')} · {exp.n_ticks} {t('detail.unitTicks')} · {exp.persona_set}
                  </div>
                </div>
                <div className="text-right text-xs text-surface-400">
                  <div>{new Date(exp.started_at).toLocaleDateString()}</div>
                  <div>{exp.elapsed_s ? `${exp.elapsed_s}s` : '—'}</div>
                </div>
              </a>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2">
              <div className="text-sm text-surface-400">
                {t('exp.pageOf', { current: currentPage, total: totalPages })}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setOffset((p) => Math.max(0, p - PAGE_SIZE))}
                  disabled={offset === 0}
                  className="btn-secondary p-2 disabled:opacity-40"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setOffset((p) => p + PAGE_SIZE)}
                  disabled={offset + PAGE_SIZE >= total}
                  className="btn-secondary p-2 disabled:opacity-40"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
