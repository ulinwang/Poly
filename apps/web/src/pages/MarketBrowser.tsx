import { useEffect, useState, useMemo, useRef, useCallback, memo } from 'react';
import {
  TrendingUp, Landmark, Trophy, Bitcoin, Gamepad2, Brain, Music,
  Globe, Droplets, Vote, Search, Tag, RefreshCw, Loader2, Layers, Sparkles, X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { api } from '../lib/api';
import { useMarketStore } from '../stores';
import { useI18n } from '../lib/i18n';
import {
  ALL_MARKETS_CATEGORY,
  deriveCategoryOptions,
  filterEventsByCategory,
  normalizeCategory,
} from '../lib/marketFilters';
import type { EventSummary } from '../types';

// Icon hints for well-known category labels (falls back to a generic tag icon).
const CATEGORY_ICONS: Record<string, LucideIcon> = {
  politics: Landmark,
  sports: Trophy,
  crypto: Bitcoin,
  esports: Gamepad2,
  tech: Brain,
  culture: Music,
  economy: Globe,
  weather: Droplets,
  elections: Vote,
  trending: TrendingUp,
};

const PAGE_SIZE = 30;
const MAX_CATEGORY_TABS = 11;

export default function MarketBrowser() {
  const { t } = useI18n();
  // `loading` = first-page load (drives skeleton); `loadingMore` = subsequent pages.
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);
  const [feedStatus, setFeedStatus] = useState<'live' | 'stale' | 'unavailable'>('live');
  const [loadError, setLoadError] = useState<string | null>(null);
  const events = useMarketStore(useShallow((s) => s.events));
  const setEvents = useMarketStore((s) => s.setEvents);
  const appendEvents = useMarketStore((s) => s.appendEvents);
  const category = useMarketStore((s) => s.category);
  const setCategory = useMarketStore((s) => s.setCategory);
  const searchQuery = useMarketStore((s) => s.searchQuery);
  const setSearchQuery = useMarketStore((s) => s.setSearchQuery);

  // Next page offset, kept in a ref so the IntersectionObserver callback always
  // reads the current value without needing to re-subscribe.
  const offsetRef = useRef(0);
  const loadingRef = useRef(false);
  const hasMoreRef = useRef(true);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // First page: replace. Resets whenever the search query or refresh changes.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setHasMore(true);
    hasMoreRef.current = true;
    loadingRef.current = true;
    offsetRef.current = 0;
    setLoadError(null);
    api.listEvents({ q: searchQuery, limit: PAGE_SIZE, offset: 0 })
      .then((res) => {
        if (cancelled) return;
        setFeedStatus(res.source ?? 'live');
        setLoadError(res.source === 'unavailable' ? (res.message || t('market.upstreamUnavailable')) : null);
        setEvents(res.events);
        offsetRef.current = PAGE_SIZE;
        const more = res.hasMore ?? res.events.length >= PAGE_SIZE;
        setHasMore(more);
        hasMoreRef.current = more;
      })
      .catch((err) => {
        if (cancelled) return;
        setFeedStatus('unavailable');
        setLoadError((err as Error).message);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
        loadingRef.current = false;
      });
    return () => { cancelled = true; };
  }, [searchQuery, setEvents, refreshTick, t]);

  // Subsequent pages: append.
  const loadMore = useCallback(() => {
    if (loadingRef.current || !hasMoreRef.current) return;
    loadingRef.current = true;
    setLoadingMore(true);
    const offset = offsetRef.current;
    api.listEvents({ q: searchQuery, limit: PAGE_SIZE, offset })
      .then((res) => {
        appendEvents(res.events);
        offsetRef.current = offset + PAGE_SIZE;
        const more = res.hasMore ?? res.events.length >= PAGE_SIZE;
        setHasMore(more);
        hasMoreRef.current = more;
      })
      .catch((err) => console.error('Failed to load more events:', err))
      .finally(() => {
        setLoadingMore(false);
        loadingRef.current = false;
      });
  }, [searchQuery, appendEvents]);

  // Bottom sentinel: trigger the next page when it scrolls into view.
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) loadMore();
    }, { rootMargin: '400px' });
    observer.observe(node);
    return () => observer.disconnect();
  }, [loadMore]);

  const allCategories = useMemo(
    () => deriveCategoryOptions(events, Number.POSITIVE_INFINITY),
    [events],
  );
  const categories = allCategories.slice(0, MAX_CATEGORY_TABS);
  const filtered = useMemo(
    () => filterEventsByCategory(events, category),
    [events, category],
  );
  const selectedCategoryKey = normalizeCategory(category);
  const hasActiveFilters = category !== ALL_MARKETS_CATEGORY || searchQuery.trim().length > 0;

  // A search refresh can remove the previously selected category from the
  // available result set. Never leave a hidden, impossible-to-clear filter.
  useEffect(() => {
    if (loading || category === ALL_MARKETS_CATEGORY) return;
    if (!allCategories.some((option) => option.key === selectedCategoryKey)) {
      setCategory(ALL_MARKETS_CATEGORY);
    }
  }, [allCategories, category, loading, selectedCategoryKey, setCategory]);

  const clearFilters = () => {
    setCategory(ALL_MARKETS_CATEGORY);
    setSearchQuery('');
  };

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <section className="relative overflow-hidden rounded-[26px] border border-white/80 bg-gradient-to-br from-[#073e38] via-[#0b655b] to-[#139688] px-5 py-6 text-white shadow-[0_18px_48px_rgba(13,82,75,0.16)] sm:px-7 sm:py-7 dark:border-white/5">
        <div className="absolute -right-12 -top-20 h-64 w-64 rounded-full border-[38px] border-white/5" aria-hidden="true" />
        <div className="absolute -bottom-28 right-28 h-56 w-56 rounded-full bg-cyan-300/10 blur-2xl" aria-hidden="true" />
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="max-w-2xl">
            <span className="mb-2.5 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-semibold text-primary-50 backdrop-blur-sm">
              <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary-200 opacity-60" /><span className="relative inline-flex h-2 w-2 rounded-full bg-primary-200" /></span>
              {t('market.liveFeed')}
            </span>
            <h2 className="text-2xl font-extrabold tracking-[-0.035em] sm:text-3xl">{t('market.heroTitle')}</h2>
            <p className="mt-2 max-w-xl text-sm leading-6 text-primary-50/75">{t('market.heroSubtitle')}</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-white/15 bg-white/10 px-4 py-3 backdrop-blur-sm">
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-primary-100/70">{t('market.available')}</p>
              <p className="mt-0.5 text-2xl font-bold tabular-nums">{events.length}</p>
            </div>
            <button
              onClick={() => setRefreshTick((n) => n + 1)}
              disabled={loading}
              title={t('market.refreshMarkets')}
              className="grid h-[54px] w-[54px] place-items-center rounded-2xl border border-white/15 bg-white text-primary-700 shadow-lg transition-transform hover:-translate-y-0.5 disabled:opacity-50"
            >
              <RefreshCw className={`h-5 w-5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-[22px] border border-white/80 bg-white/70 p-3 shadow-sm backdrop-blur-sm dark:border-white/5 dark:bg-white/5 sm:p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">{t('nav.searchMarkets')}</span>
            <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-400" />
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={t('nav.searchMarkets')}
              className="h-11 w-full rounded-xl border border-surface-200 bg-white pl-10 pr-10 text-sm text-surface-900 outline-none transition focus:border-primary-400 focus:ring-4 focus:ring-primary-500/10 dark:border-white/10 dark:bg-surface-900/70 dark:text-surface-100"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-lg text-surface-400 hover:bg-surface-100 hover:text-surface-700 dark:hover:bg-white/10 dark:hover:text-white"
                aria-label={t('market.clearFilters')}
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </label>
          {hasActiveFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex h-10 shrink-0 items-center justify-center gap-1.5 rounded-xl px-3 text-sm font-semibold text-surface-500 transition hover:bg-surface-100 hover:text-surface-900 dark:text-surface-400 dark:hover:bg-white/10 dark:hover:text-white"
            >
              <X className="h-4 w-4" />
              {t('market.clearFilters')}
            </button>
          )}
        </div>

        <div className="mt-3 flex items-center gap-2 overflow-x-auto pb-0.5 scrollbar-hide" aria-label={t('market.filterByCategory')}>
          {[{ key: normalizeCategory(ALL_MARKETS_CATEGORY), label: ALL_MARKETS_CATEGORY, count: events.length }, ...categories].map((option) => {
          const Icon = option.label === ALL_MARKETS_CATEGORY ? undefined : (CATEGORY_ICONS[option.key] ?? Tag);
          const active = selectedCategoryKey === option.key;
          return (
            <button
              key={option.key}
              type="button"
              onClick={() => setCategory(option.label)}
              aria-pressed={active}
              className={`flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-semibold whitespace-nowrap transition-all ${
                active
                  ? 'bg-primary-600 text-white shadow-sm'
                  : 'border border-surface-200/80 bg-white/80 text-surface-600 hover:border-primary-200 hover:text-primary-700 dark:border-white/10 dark:bg-white/5 dark:text-surface-300 dark:hover:text-white'
              }`}
            >
              {Icon && <Icon className="w-3.5 h-3.5" />}
              {option.label === ALL_MARKETS_CATEGORY ? t('market.all') : option.label}
              <span className={`rounded-md px-1.5 py-0.5 text-[10px] tabular-nums ${active ? 'bg-white/15 text-white' : 'bg-surface-100 text-surface-400 dark:bg-white/10 dark:text-surface-400'}`}>
                {option.count}
              </span>
            </button>
          );
        })}
        </div>
      </section>

      {feedStatus !== 'live' && (
        <div className={`flex flex-col gap-3 rounded-2xl border px-4 py-4 sm:flex-row sm:items-center sm:justify-between ${
          feedStatus === 'stale'
            ? 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200'
            : 'border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200'
        }`}>
          <div>
            <p className="text-sm font-semibold">
              {feedStatus === 'stale' ? t('market.staleData') : t('market.loadFailed')}
            </p>
            <p className="mt-1 text-xs opacity-75">{loadError || t('market.upstreamUnavailable')}</p>
          </div>
          <button
            type="button"
            onClick={() => setRefreshTick((value) => value + 1)}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-current/20 bg-white/70 px-3 py-2 text-sm font-semibold dark:bg-black/10"
          >
            <RefreshCw className="h-4 w-4" />
            {t('market.retry')}
          </button>
        </div>
      )}

      {/* Section title */}
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-primary-600 dark:text-primary-400"><Sparkles className="h-3.5 w-3.5" />{t('market.discover')}</div>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-surface-900 dark:text-white">{category === ALL_MARKETS_CATEGORY ? t('market.all') : category}</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className="rounded-full border border-surface-200 bg-white/70 px-3 py-1.5 text-xs font-semibold text-surface-500 dark:border-white/10 dark:bg-white/5 dark:text-surface-400">{t('market.countEvents', { count: filtered.length })}</span>
        </div>
      </div>

      {/* Event grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card p-5 space-y-4 animate-pulse">
              <div className="flex items-start gap-3">
                <div className="w-12 h-12 rounded-xl bg-surface-200 dark:bg-surface-700 flex-shrink-0" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-surface-200 dark:bg-surface-700 rounded w-3/4" />
                  <div className="h-3 bg-surface-200 dark:bg-surface-700 rounded w-1/2" />
                </div>
              </div>
              <div className="h-10 bg-surface-200 dark:bg-surface-700 rounded" />
              <div className="h-3 bg-surface-200 dark:bg-surface-700 rounded w-1/3" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 && feedStatus === 'unavailable' ? null : filtered.length === 0 ? (
        <div className="text-center py-20 text-surface-400">
          <Search className="w-12 h-12 mx-auto mb-4 text-surface-300 dark:text-surface-600" />
          <p className="text-lg mb-1 font-medium">{t('market.noneFound')}</p>
          <p className="text-sm">{t('market.adjustSearch')}</p>
        </div>
      ) : (
        <EventGrid events={filtered} />
      )}

      {/* Infinite-scroll sentinel + load-more indicator. The category tabs are a
          client-side filter on already-loaded events, so the sentinel keeps
          fetching the underlying unfiltered list as long as the server has more. */}
      {!loading && (
        <div ref={sentinelRef} className="h-10 flex items-center justify-center">
          {loadingMore && (
            <span className="flex items-center gap-2 text-sm text-surface-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              {t('common.loading')}
            </span>
          )}
          {!hasMore && events.length > 0 && (
            <span className="text-xs text-surface-400">{t('common.noMore')}</span>
          )}
        </div>
      )}
    </div>
  );
}

function EventGrid({ events }: { events: EventSummary[] }) {
  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
      {events.map((event) => (
        event.is_single
          ? <SingleEventCard key={event.event_slug} event={event} />
          : <EventCard key={event.event_slug} event={event} />
      ))}
    </div>
  );
}

function formatVol(v: number) {
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}k`;
  return `$${v.toFixed(0)}`;
}

function hashString(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

// Deterministic emoji/icon based on slug
function marketIcon(slug: string): string {
  const icons = ['🗳️', '💰', '⚽', '🎮', '🎵', '🌤️', '🏛️', '🚀', '🔬', '🌍', '🔥', '⚡'];
  return icons[hashString(slug) % icons.length];
}

// Deterministic color for icon background
function marketIconBg(slug: string): string {
  const bgs = [
    'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400',
    'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400',
    'bg-violet-50 text-violet-600 dark:bg-violet-900/20 dark:text-violet-400',
    'bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400',
    'bg-rose-50 text-rose-600 dark:bg-rose-900/20 dark:text-rose-400',
    'bg-cyan-50 text-cyan-600 dark:bg-cyan-900/20 dark:text-cyan-400',
  ];
  return bgs[hashString(slug) % bgs.length];
}

// Convert a YES probability (0..1) to whole cents. Returns null for null/NaN
// input so callers can render a non-misleading placeholder.
function toCents(p: number | null | undefined): number | null {
  if (p == null || !Number.isFinite(p)) return null;
  return Math.round(p * 100);
}

// Square thumbnail that shows a real image when available, falling back to a
// deterministic emoji color block (keyed by slug) if the URL is empty or the
// image fails to load.
function Thumbnail({
  src, seed, size = 'w-12 h-12 text-xl',
}: { src?: string | null; seed: string; size?: string }) {
  const [failed, setFailed] = useState(false);
  const showImg = !!src && !failed;
  if (showImg) {
    return (
      <img
        src={src!}
        alt=""
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
        className={`${size} rounded-xl object-cover flex-shrink-0 bg-surface-100 dark:bg-surface-700`}
      />
    );
  }
  return (
    <div className={`${size} rounded-xl flex-shrink-0 flex items-center justify-center ${marketIconBg(seed)}`}>
      {marketIcon(seed)}
    </div>
  );
}

function CategoryBadges({ categories }: { categories: string[] }) {
  const unique = new Map<string, string>();
  for (const rawLabel of categories) {
    const label = rawLabel.trim();
    const key = normalizeCategory(label);
    if (key && !unique.has(key)) unique.set(key, label);
  }
  const visible = [...unique.entries()].slice(0, 2);
  if (visible.length === 0) return null;

  return (
    <div className="mt-2 flex min-w-0 items-center gap-1.5">
      {visible.map(([key, label]) => (
        <span
          key={key}
          className="max-w-32 truncate rounded-md bg-surface-100 px-2 py-0.5 text-[10px] font-medium text-surface-500 dark:bg-white/5 dark:text-surface-400"
        >
          {label}
        </span>
      ))}
    </div>
  );
}

// Single binary event: rendered as an ordinary Yes/No market card. The single
// outcome carries the live YES quote; "No" is its complement. Clicking opens
// the sub-market detail page.
const SingleEventCard = memo(function SingleEventCard({ event }: { event: EventSummary }) {
  const { t } = useI18n();
  const yesCents = toCents(event.outcomes[0]?.price);
  const target = event.primary_slug || event.outcomes[0]?.slug || '';

  return (
    <a
      href={`#/markets/${target}`}
      className="card card-hover p-5 flex flex-col gap-4 group"
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        <Thumbnail src={event.icon_url} seed={event.event_slug} />
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-surface-800 dark:text-surface-100 line-clamp-2 leading-snug">
            {event.title}
          </h3>
          <div className="flex items-center gap-2 mt-1.5">
            <span className="badge text-[10px] badge-live">
              {t('market.open')}
            </span>
            <span className="text-xs text-surface-400">
              {formatVol(event.volume)} {t('market.vol')}
            </span>
          </div>
          <CategoryBadges categories={event.categories} />
        </div>
      </div>

      {/* Binary market: Yes / No prices (real Polymarket quote; — when none) */}
      <div className="flex items-center gap-3">
        <div className="flex-1 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg px-3 py-2 text-center">
          <div className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">{t('market.yes')}</div>
          <div className="text-lg font-bold text-emerald-700 dark:text-emerald-300">
            {yesCents == null ? '—' : `${yesCents}¢`}
          </div>
        </div>
        <div className="flex-1 bg-rose-50 dark:bg-rose-900/20 rounded-lg px-3 py-2 text-center">
          <div className="text-xs text-rose-600 dark:text-rose-400 font-medium">{t('market.no')}</div>
          <div className="text-lg font-bold text-rose-700 dark:text-rose-300">
            {yesCents == null ? '—' : `${100 - yesCents}¢`}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-surface-400 dark:text-surface-500 pt-2 border-t border-surface-100 dark:border-surface-700/50 mt-auto">
        <span className="font-mono text-[10px]">{event.event_slug.slice(0, 10)}…</span>
      </div>
    </a>
  );
});

// Multi-outcome event card: lists up to 4 sub-market outcomes (label + that
// sub-market's live YES price). Clicking enters the event via its primary
// sub-market slug — MarketDetail then surfaces the sibling outcomes. No
// single-market "Open" badge is shown, since it would misrepresent the event.
const EventCard = memo(function EventCard({ event }: { event: EventSummary }) {
  const { t } = useI18n();
  const shown = event.outcomes.slice(0, 4);
  const extra = event.outcomes.length - shown.length;
  const target = event.primary_slug || event.outcomes[0]?.slug || '';

  return (
    <a
      href={`#/markets/${target}`}
      className="card card-hover p-5 flex flex-col gap-4 group"
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        <Thumbnail src={event.icon_url} seed={event.event_slug} />
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-surface-800 dark:text-surface-100 line-clamp-2 leading-snug">
            {event.title}
          </h3>
          <div className="flex items-center gap-2 mt-1.5">
            <span className="badge text-[10px] inline-flex items-center gap-1 bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-300">
              <Layers className="w-3 h-3" />
              {t('market.outcomes', { count: event.n_outcomes })}
            </span>
            <span className="text-xs text-surface-400">
              {formatVol(event.volume)} {t('market.vol')}
            </span>
          </div>
          <CategoryBadges categories={event.categories} />
        </div>
      </div>

      {/* Outcome list with mini Yes prices */}
      <div className="space-y-1.5">
        {shown.map((o, i) => {
          const cents = toCents(o.price);
          return (
            <div
              key={o.slug || `${o.label}:${i}`}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-surface-50 dark:bg-surface-700/40"
            >
              <span className="text-xs text-surface-700 dark:text-surface-200 truncate flex-1">
                {o.label}
              </span>
              <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex-shrink-0">
                {cents == null ? '—' : `${cents}¢`}
              </span>
            </div>
          );
        })}
        {extra > 0 && (
          <div className="px-2.5 text-xs text-surface-400">{t('market.moreOutcomes', { count: extra })}</div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-surface-400 dark:text-surface-500 pt-2 border-t border-surface-100 dark:border-surface-700/50 mt-auto">
        <span>{t('market.multiOutcomeEvent')}</span>
        <span className="font-mono text-[10px]">{event.event_slug.slice(0, 10)}…</span>
      </div>
    </a>
  );
});
