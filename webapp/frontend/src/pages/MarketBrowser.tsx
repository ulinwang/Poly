import { useEffect, useState } from 'react';
import { TrendingUp, Flame, Globe, Trophy, Bitcoin, Gamepad2, Landmark, Brain, Music, Droplets, Vote, MoreHorizontal } from 'lucide-react';
import { api } from '../lib/api';
import { useMarketStore } from '../stores';
import type { Market } from '../types';

const CATEGORIES = [
  { id: 'All', label: 'All', icon: null },
  { id: 'Trending', label: 'Trending', icon: TrendingUp },
  { id: 'Breaking', label: 'Breaking', icon: Flame },
  { id: 'Politics', label: 'Politics', icon: Landmark },
  { id: 'Sports', label: 'Sports', icon: Trophy },
  { id: 'Crypto', label: 'Crypto', icon: Bitcoin },
  { id: 'Esports', label: 'Esports', icon: Gamepad2 },
  { id: 'Tech', label: 'Tech', icon: Brain },
  { id: 'Culture', label: 'Culture', icon: Music },
  { id: 'Economy', label: 'Economy', icon: Globe },
  { id: 'Weather', label: 'Weather', icon: Droplets },
  { id: 'Elections', label: 'Elections', icon: Vote },
  { id: 'More', label: 'More', icon: MoreHorizontal },
];

export default function MarketBrowser() {
  const [loading, setLoading] = useState(false);
  const markets = useMarketStore((s) => s.markets);
  const setMarkets = useMarketStore((s) => s.setMarkets);
  const category = useMarketStore((s) => s.category);
  const setCategory = useMarketStore((s) => s.setCategory);
  const searchQuery = useMarketStore((s) => s.searchQuery);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.listMarkets({ q: searchQuery, live_only: true, limit: 50 })
      .then((res) => {
        if (!cancelled) setMarkets(res.markets);
      })
      .catch((err) => console.error('Failed to load markets:', err))
      .finally(() => setLoading(false));
    return () => { cancelled = true; };
  }, [searchQuery, setMarkets]);

  const filtered = category === 'All'
    ? markets
    : markets.filter((m) => {
        const q = m.question?.toLowerCase() || '';
        const slug = m.slug?.toLowerCase() || '';
        return q.includes(category.toLowerCase()) || slug.includes(category.toLowerCase());
      });

  return (
    <div className="space-y-6">
      {/* Category Tabs */}
      <div className="flex gap-1 overflow-x-auto pb-2 scrollbar-hide">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setCategory(cat.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
              category === cat.id
                ? 'bg-surface-800 dark:bg-white text-white dark:text-surface-900'
                : 'bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400 hover:bg-surface-200 dark:hover:bg-surface-700'
            }`}
          >
            {cat.icon && <cat.icon className="w-3.5 h-3.5" />}
            {cat.label}
          </button>
        ))}
      </div>

      {/* Market Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card p-4 space-y-3 animate-pulse">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-surface-200 dark:bg-surface-700 flex-shrink-0" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-surface-200 dark:bg-surface-700 rounded w-3/4" />
                  <div className="h-3 bg-surface-200 dark:bg-surface-700 rounded w-1/2" />
                </div>
              </div>
              <div className="h-8 bg-surface-200 dark:bg-surface-700 rounded" />
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
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((market) => (
            <MarketCard key={market.slug} market={market} />
          ))}
        </div>
      )}
    </div>
  );
}

function MarketCard({ market }: { market: Market }) {
  const formatVol = (v: number) => {
    if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
    if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}k`;
    return `$${v.toFixed(0)}`;
  };

  return (
    <a
      href={`#/markets/${market.slug}`}
      className="card p-4 hover:shadow-md transition-shadow flex flex-col gap-3"
    >
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-lg flex-shrink-0 flex items-center justify-center text-lg ${
          market.is_live
            ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-600'
            : 'bg-surface-100 dark:bg-surface-700 text-surface-400'
        }`}>
          {market.is_live ? '🟢' : '🔴'}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-surface-800 dark:text-surface-100 line-clamp-2 leading-snug">
            {market.question || market.slug}
          </h3>
          <div className="flex items-center gap-2 mt-1">
            <span className={`badge text-[10px] ${market.is_live ? 'badge-live' : 'badge-resolved'}`}>
              {market.is_live ? 'Open' : 'Resolved'}
            </span>
            <span className="text-xs text-surface-400">
              Vol {formatVol(market.volume)}
            </span>
          </div>
        </div>
      </div>

      {/* Mini price sparkline placeholder */}
      <div className="h-8 flex items-end gap-0.5">
        {Array.from({ length: 20 }).map((_, i) => {
          const h = 20 + Math.random() * 60;
          return (
            <div
              key={i}
              className="flex-1 rounded-sm bg-primary-200 dark:bg-primary-800/50"
              style={{ height: `${h}%` }}
            />
          );
        })}
      </div>

      <div className="flex items-center justify-between text-xs text-surface-500 dark:text-surface-400">
        <span>Condition: {market.condition_id.slice(0, 8)}...</span>
        <span>{market.n_holders?.toLocaleString() || 0} holders</span>
      </div>
    </a>
  );
}
