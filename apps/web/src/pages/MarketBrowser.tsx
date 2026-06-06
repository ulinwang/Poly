import { useEffect, useState, useMemo, useRef, useCallback, memo } from 'react';
import {
  TrendingUp, Landmark, Trophy, Bitcoin, Gamepad2, Brain, Music,
  Globe, Droplets, Vote, Search, Tag, RefreshCw, Loader2, Layers,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api } from '../lib/api';
import { useMarketStore } from '../stores';
import type { Market } from '../types';

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

// Derive category tabs from the loaded markets, ranked by how many markets
// carry each tag. Guarantees every tab actually has content when clicked.
function deriveCategories(markets: Market[]): string[] {
  const counts = new Map<string, number>();
  for (const m of markets) {
    for (const c of m.categories ?? []) {
      counts.set(c, (counts.get(c) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_TABS)
    .map(([label]) => label);
}

export default function MarketBrowser() {
  // `loading` = first-page load (drives skeleton); `loadingMore` = subsequent pages.
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);
  const markets = useMarketStore((s) => s.markets);
  const setMarkets = useMarketStore((s) => s.setMarkets);
  const appendMarkets = useMarketStore((s) => s.appendMarkets);
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
    api.listMarkets({ q: searchQuery, live_only: true, limit: PAGE_SIZE, offset: 0 })
      .then((res) => {
        if (cancelled) return;
        setMarkets(res.markets);
        offsetRef.current = PAGE_SIZE;
        const more = res.hasMore ?? res.markets.length >= PAGE_SIZE;
        setHasMore(more);
        hasMoreRef.current = more;
      })
      .catch((err) => console.error('Failed to load markets:', err))
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
        loadingRef.current = false;
      });
    return () => { cancelled = true; };
  }, [searchQuery, setMarkets, refreshTick]);

  // Subsequent pages: append.
  const loadMore = useCallback(() => {
    if (loadingRef.current || !hasMoreRef.current) return;
    loadingRef.current = true;
    setLoadingMore(true);
    const offset = offsetRef.current;
    api.listMarkets({ q: searchQuery, live_only: true, limit: PAGE_SIZE, offset })
      .then((res) => {
        appendMarkets(res.markets);
        offsetRef.current = offset + PAGE_SIZE;
        const more = res.hasMore ?? res.markets.length >= PAGE_SIZE;
        setHasMore(more);
        hasMoreRef.current = more;
      })
      .catch((err) => console.error('Failed to load more markets:', err))
      .finally(() => {
        setLoadingMore(false);
        loadingRef.current = false;
      });
  }, [searchQuery, appendMarkets]);

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

  const categories = useMemo(() => deriveCategories(markets), [markets]);

  const filtered = useMemo(() => (
    category === 'All'
      ? markets
      : markets.filter((m) => (m.categories ?? []).includes(category))
  ), [markets, category]);

  // Group the (filtered) markets by event_slug. An event with multiple
  // sub-markets renders as a single multi-outcome card; events with one market
  // (or no event_slug) render as ordinary market cards. Order is preserved from
  // the underlying volume-sorted feed (anchored on each event's first market).
  const displayItems = useMemo(() => groupByEvent(filtered), [filtered]);

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
          placeholder="搜索市场…"
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
              {cat}
            </button>
          );
        })}
      </div>

      {/* Section title */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-surface-900 dark:text-white">{category}</h2>
        <div className="flex items-center gap-3">
          <span className="text-sm text-surface-400">{filtered.length} markets</span>
          <button
            onClick={() => setRefreshTick((n) => n + 1)}
            disabled={loading}
            title="刷新市场数据"
            className="p-2 rounded-lg text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Market grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
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
          <p className="text-lg mb-1">No markets found</p>
          <p className="text-sm">Try adjusting your search or category filter.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {displayItems.map((item) => (
            item.kind === 'event'
              ? <EventCard key={`event:${item.eventSlug}`} group={item} />
              : <MarketCard key={item.market.slug} market={item.market} />
          ))}
        </div>
      )}

      {/* Infinite-scroll sentinel + load-more indicator. The category tabs are a
          client-side filter on already-loaded markets, so the sentinel keeps
          fetching the underlying unfiltered list as long as the server has more. */}
      {!loading && (
        <div ref={sentinelRef} className="h-10 flex items-center justify-center">
          {loadingMore && (
            <span className="flex items-center gap-2 text-sm text-surface-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              加载中…
            </span>
          )}
          {!hasMore && markets.length > 0 && (
            <span className="text-xs text-surface-400">没有更多市场了</span>
          )}
        </div>
      )}
    </div>
  );
}

function formatVol(v: number) {
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}k`;
  return `$${v.toFixed(0)}`;
}

// A browser row is either a standalone market card or a grouped event card.
type SingleItem = { kind: 'single'; market: Market };
type EventItem = {
  kind: 'event';
  eventSlug: string;
  title: string;
  markets: Market[];
  volume: number;
};
type DisplayItem = SingleItem | EventItem;

// Strip a trailing " - <group_title>" / " <group_title>" suffix so the event
// card shows the shared question rather than one sub-market's outcome.
function eventTitle(market: Market): string {
  const q = market.question || market.slug;
  const g = market.group_title;
  if (g && q.endsWith(g)) {
    return q.slice(0, q.length - g.length).replace(/[\s\-–—:|]+$/, '').trim() || q;
  }
  return q;
}

// Group markets by event_slug, preserving feed order. Events with 2+ markets
// become a single EventItem; everything else stays a SingleItem.
function groupByEvent(markets: Market[]): DisplayItem[] {
  const order: string[] = [];
  const groups = new Map<string, Market[]>();
  const singles: SingleItem[] = [];

  for (const m of markets) {
    const ev = m.event_slug;
    if (!ev) {
      // No event slug — always standalone. Key by index implicitly via push.
      singles.push({ kind: 'single', market: m });
      order.push(`single:${m.slug}`);
      continue;
    }
    if (!groups.has(ev)) {
      groups.set(ev, []);
      order.push(`event:${ev}`);
    }
    groups.get(ev)!.push(m);
  }

  const singleBySlug = new Map(singles.map((s) => [`single:${s.market.slug}`, s]));
  const items: DisplayItem[] = [];
  for (const key of order) {
    if (key.startsWith('single:')) {
      const s = singleBySlug.get(key);
      if (s) items.push(s);
      continue;
    }
    const ev = key.slice('event:'.length);
    const ms = groups.get(ev)!;
    if (ms.length <= 1) {
      items.push({ kind: 'single', market: ms[0] });
    } else {
      items.push({
        kind: 'event',
        eventSlug: ev,
        title: eventTitle(ms[0]),
        markets: ms,
        volume: ms.reduce((sum, m) => sum + (m.volume || 0), 0),
      });
    }
  }
  return items;
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

const MarketCard = memo(function MarketCard({ market }: { market: Market }) {
  const sparkline = useMemo(() => {
    const seed = hashString(market.slug);
    const rng = (n: number) => {
      const x = Math.sin(seed + n) * 10000;
      return x - Math.floor(x);
    };
    return Array.from({ length: 20 }, (_, i) => 30 + rng(i) * 50);
  }, [market.slug]);

  const yesPrice = useMemo(() => {
    const h = hashString(market.slug + 'yes');
    return (h % 100);
  }, [market.slug]);

  const icon = marketIcon(market.slug);
  const iconBg = marketIconBg(market.slug);

  return (
    <a
      href={`#/markets/${market.slug}`}
      className="card p-5 hover:shadow-md transition-shadow flex flex-col gap-4 group"
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className={`w-12 h-12 rounded-xl flex-shrink-0 flex items-center justify-center text-xl ${iconBg}`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-surface-800 dark:text-surface-100 line-clamp-2 leading-snug">
            {market.question || market.slug}
          </h3>
          <div className="flex items-center gap-2 mt-1.5">
            <span className={`badge text-[10px] ${market.is_live ? 'badge-live' : 'badge-resolved'}`}>
              {market.is_live ? 'Open' : 'Resolved'}
            </span>
            <span className="text-xs text-surface-400">
              {formatVol(market.volume)} Vol
            </span>
          </div>
        </div>
      </div>

      {/* Yes / No prices */}
      <div className="flex items-center gap-3">
        <div className="flex-1 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg px-3 py-2 text-center">
          <div className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">Yes</div>
          <div className="text-lg font-bold text-emerald-700 dark:text-emerald-300">{yesPrice}¢</div>
        </div>
        <div className="flex-1 bg-rose-50 dark:bg-rose-900/20 rounded-lg px-3 py-2 text-center">
          <div className="text-xs text-rose-600 dark:text-rose-400 font-medium">No</div>
          <div className="text-lg font-bold text-rose-700 dark:text-rose-300">{100 - yesPrice}¢</div>
        </div>
      </div>

      {/* Sparkline */}
      <div className="h-8 flex items-end gap-[3px]">
        {sparkline.map((h, i) => (
          <div
            key={i}
            className="flex-1 rounded-sm bg-primary-200/70 dark:bg-primary-800/40"
            style={{ height: `${h}%` }}
          />
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-surface-400 dark:text-surface-500 pt-2 border-t border-surface-100 dark:border-surface-700/50">
        <span>{market.n_holders?.toLocaleString() || 0} traders</span>
        <span className="font-mono text-[10px]">{market.condition_id.slice(0, 6)}…</span>
      </div>
    </a>
  );
});

// Multi-outcome event card: lists up to 4 sub-market outcomes (group_title +
// a deterministic mini Yes price). Clicking enters the event via its first
// sub-market's slug — MarketDetail then surfaces the sibling outcomes.
const EventCard = memo(function EventCard({ group }: { group: EventItem }) {
  const outcomes = group.markets.slice(0, 4);
  const extra = group.markets.length - outcomes.length;
  const icon = marketIcon(group.eventSlug);
  const iconBg = marketIconBg(group.eventSlug);
  const target = group.markets[0]?.slug ?? '';

  return (
    <a
      href={`#/markets/${target}`}
      className="card p-5 hover:shadow-md transition-shadow flex flex-col gap-4 group"
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className={`w-12 h-12 rounded-xl flex-shrink-0 flex items-center justify-center text-xl ${iconBg}`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-surface-800 dark:text-surface-100 line-clamp-2 leading-snug">
            {group.title}
          </h3>
          <div className="flex items-center gap-2 mt-1.5">
            <span className="badge text-[10px] inline-flex items-center gap-1 bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-300">
              <Layers className="w-3 h-3" />
              {group.markets.length} 个结果
            </span>
            <span className="text-xs text-surface-400">
              {formatVol(group.volume)} Vol
            </span>
          </div>
        </div>
      </div>

      {/* Outcome list with mini Yes prices */}
      <div className="space-y-1.5">
        {outcomes.map((m) => {
          const yesPrice = hashString(m.slug + 'yes') % 100;
          return (
            <div
              key={m.slug}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-surface-50 dark:bg-surface-700/40"
            >
              <span className="text-xs text-surface-700 dark:text-surface-200 truncate flex-1">
                {m.group_title || m.question || m.slug}
              </span>
              <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex-shrink-0">
                {yesPrice}¢
              </span>
            </div>
          );
        })}
        {extra > 0 && (
          <div className="px-2.5 text-xs text-surface-400">+{extra} 个结果</div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-surface-400 dark:text-surface-500 pt-2 border-t border-surface-100 dark:border-surface-700/50 mt-auto">
        <span>多结果事件</span>
        <span className="font-mono text-[10px]">{group.eventSlug.slice(0, 10)}…</span>
      </div>
    </a>
  );
});
