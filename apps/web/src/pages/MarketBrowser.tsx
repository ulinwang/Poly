import { useEffect, useState, useMemo, useRef, useCallback, memo } from 'react';
import {
  TrendingUp, Landmark, Trophy, Bitcoin, Gamepad2, Brain, Music,
  Globe, Droplets, Vote, Search, Tag, RefreshCw, Loader2, Layers,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useShallow } from 'zustand/react/shallow';
import { api } from '../lib/api';
import { useMarketStore } from '../stores';
import { useI18n } from '../lib/i18n';
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

const MAX_TABS = 11;
const PAGE_SIZE = 30;

// Derive category tabs from the loaded events, ranked by how many events carry
// each tag. Guarantees every tab actually has content when clicked.
function deriveCategories(events: EventSummary[]): string[] {
  const counts = new Map<string, number>();
  for (const ev of events) {
    for (const c of ev.categories ?? []) {
      counts.set(c, (counts.get(c) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_TABS)
    .map(([label]) => label);
}

export default function MarketBrowser() {
  const { t } = useI18n();
  // `loading` = first-page load (drives skeleton); `loadingMore` = subsequent pages.
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);
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
    api.listEvents({ q: searchQuery, limit: PAGE_SIZE, offset: 0 })
      .then((res) => {
        if (cancelled) return;
        setEvents(res.events);
        offsetRef.current = PAGE_SIZE;
        const more = res.hasMore ?? res.events.length >= PAGE_SIZE;
        setHasMore(more);
        hasMoreRef.current = more;
      })
      .catch((err) => console.error('Failed to load events:', err))
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
        loadingRef.current = false;
      });
    return () => { cancelled = true; };
  }, [searchQuery, setEvents, refreshTick]);

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

  const categories = useMemo(() => deriveCategories(events), [events]);

  const filtered = useMemo(() => (
    category === 'All'
      ? events
      : events.filter((ev) => (ev.categories ?? []).includes(category))
  ), [events, category]);

  const tabs = ['All', ...categories];

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      {/* Search bar (mobile — desktop search lives in the top nav) */}
      <div className="lg:hidden relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={t('nav.searchMarkets')}
          className="w-full pl-9 pr-4 py-2.5 bg-white dark:bg-surface-800 border border-surface-200 dark:border-surface-700 rounded-xl text-sm text-surface-900 dark:text-surface-100 placeholder:text-surface-400 focus:ring-2 focus:ring-primary-500 focus:outline-none"
        />
      </div>

      {/* Category tabs (horizontal, Polymarket style) */}
      <div className="flex gap-1 overflow-x-auto pb-1 border-b border-surface-200 dark:border-surface-700">
        {tabs.map((cat) => {
          const Icon = cat === 'All' ? undefined : (CATEGORY_ICONS[cat.toLowerCase()] ?? Tag);
          const active = category === cat;
          return (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors border-b-2 -mb-px ${
                active
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-surface-500 dark:text-surface-400 hover:text-surface-700 dark:hover:text-surface-300'
              }`}
            >
              {Icon && <Icon className="w-3.5 h-3.5" />}
              {cat === 'All' ? t('market.all') : cat}
            </button>
          );
        })}
      </div>

      {/* Section title */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold tracking-tight text-surface-900 dark:text-white">
          {category === 'All' ? t('market.all') : category}
        </h2>
        <div className="flex items-center gap-3">
          <span className="text-sm text-surface-400">{t('market.countEvents', { count: filtered.length })}</span>
          <button
            onClick={() => setRefreshTick((n) => n + 1)}
            disabled={loading}
            title={t('market.refreshMarkets')}
            className="p-2 rounded-lg text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
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
      ) : filtered.length === 0 ? (
        <div className="text-center py-20 text-surface-400">
          <Search className="w-12 h-12 mx-auto mb-4 text-surface-300 dark:text-surface-600" />
          <p className="text-lg mb-1 font-medium">{t('market.noneFound')}</p>
          <p className="text-sm">{t('market.adjustSearch')}</p>
        </div>
      ) : (
        <VirtualEventGrid events={filtered} />
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

// Responsive virtualized grid: only renders the rows that are actually in the
// viewport. Column count is derived from the container width so the layout
// stays in sync with the Tailwind breakpoints below.
function VirtualEventGrid({ events }: { events: EventSummary[] }) {
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

  // Match the Tailwind breakpoints used below: md=768px, xl=1280px.
  const cols = width >= 1280 ? 3 : width >= 768 ? 2 : 1;
  const rows = Math.ceil(events.length / cols);

  const virtualizer = useVirtualizer({
    count: rows,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 260,
    overscan: 3,
  });

  return (
    <div
      ref={parentRef}
      className="h-[calc(100vh-240px)] overflow-y-auto scrollbar-hide"
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
          const rowEvents = events.slice(start, start + cols);
          return (
            <div
              key={virtualRow.key}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              className="absolute top-0 left-0 w-full"
              style={{ transform: `translateY(${virtualRow.start}px)` }}
            >
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                {rowEvents.map((ev) => (
                  ev.is_single
                    ? <SingleEventCard key={ev.event_slug} event={ev} />
                    : <EventCard key={ev.event_slug} event={ev} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
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
