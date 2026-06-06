import { useEffect, useState } from 'react';
import {
  BarChart3, Search, Database,
} from 'lucide-react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { api } from '../lib/api';
import { useI18n } from '../lib/i18n';
import type { Market, MarketAnalysis } from '../types';

export default function DataAnalysis() {
  const { t } = useI18n();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Market[]>([]);
  const [slug, setSlug] = useState('');
  const [analysis, setAnalysis] = useState<MarketAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounced market search for the selector.
  useEffect(() => {
    if (!query.trim()) { setResults([]); return; }
    const handle = setTimeout(() => {
      api.listMarkets({ q: query.trim(), limit: 8 })
        .then((res) => setResults(res.markets))
        .catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(handle);
  }, [query]);

  const runAnalysis = (targetSlug: string) => {
    const s = targetSlug.trim();
    if (!s) return;
    setSlug(s);
    setResults([]);
    setLoading(true);
    setError(null);
    setAnalysis(null);
    api.getMarketAnalysis(s)
      .then((res) => setAnalysis(res))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <BarChart3 className="w-6 h-6 text-primary-600" />
        <div>
          <h1 className="text-xl font-bold text-surface-900 dark:text-white">{t('analysis.title')}</h1>
          <p className="text-sm text-surface-400 mt-0.5">{t('analysis.subtitle')}</p>
        </div>
      </div>

      {/* Market selector */}
      <div className="card p-5 space-y-3">
        <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
          {t('analysis.selectMarket')}
        </label>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('analysis.searchPlaceholder')}
            className="input pl-9"
          />
        </div>

        {results.length > 0 && (
          <div className="border border-surface-200 dark:border-surface-700 rounded-lg divide-y divide-surface-200 dark:divide-surface-700 overflow-hidden">
            {results.map((m) => (
              <button
                key={m.slug}
                type="button"
                onClick={() => { setQuery(m.question); runAnalysis(m.slug); }}
                className="w-full text-left px-3 py-2 hover:bg-surface-50 dark:hover:bg-surface-700/50 transition-colors"
              >
                <div className="text-sm text-surface-800 dark:text-surface-100 truncate">{m.question}</div>
                <div className="text-xs text-surface-400 truncate">{m.slug}</div>
              </button>
            ))}
          </div>
        )}

        {/* Direct slug entry fallback */}
        <div className="flex items-center gap-2 pt-1">
          <input
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') runAnalysis(slug); }}
            placeholder={t('analysis.slugPlaceholder')}
            className="input flex-1"
          />
          <button
            type="button"
            onClick={() => runAnalysis(slug)}
            disabled={!slug.trim() || loading}
            className="btn-primary"
          >
            {t('analysis.analyze')}
          </button>
        </div>
      </div>

      {/* Results */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <div className="w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {!loading && error && (
        <div className="card p-6 text-sm text-danger">
          {t('analysis.loadFailed', { msg: error })}
        </div>
      )}

      {!loading && !error && !analysis && (
        <div className="card p-10 text-center text-sm text-surface-400">
          {t('analysis.pickPrompt')}
        </div>
      )}

      {!loading && !error && analysis && !analysis.available && (
        <div className="card p-10 flex flex-col items-center gap-3 text-center">
          <Database className="w-10 h-10 text-surface-300 dark:text-surface-600" />
          <p className="text-sm text-surface-500 dark:text-surface-400">{t('analysis.noData')}</p>
          {analysis.message && (
            <p className="text-xs text-surface-400">{analysis.message}</p>
          )}
        </div>
      )}

      {!loading && !error && analysis && analysis.available && (
        <AnalysisResult data={analysis} />
      )}
    </div>
  );
}

function AnalysisResult({ data }: { data: MarketAnalysis }) {
  const { t } = useI18n();
  const metrics = data.metrics;
  const series = data.volume_series ?? [];
  const topWallets = data.top_wallets ?? [];
  const conc = data.concentration;
  const holders = data.holders;

  const fmtNum = (n: number | undefined) =>
    n === undefined ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  const fmtUsd = (n: number | undefined) =>
    n === undefined ? '—' : `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  const fmtPct = (n: number | undefined) =>
    n === undefined ? '—' : `${(n * 100).toFixed(1)}%`;

  return (
    <div className="space-y-6">
      {data.question && (
        <div className="card p-4">
          <div className="text-xs text-surface-400 mb-1">{t('analysis.question')}</div>
          <div className="text-sm font-medium text-surface-800 dark:text-surface-100">{data.question}</div>
        </div>
      )}

      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label={t('analysis.metric.trades')} value={fmtNum(metrics?.n_trades)} />
        <MetricCard label={t('analysis.metric.notional')} value={fmtUsd(metrics?.total_notional)} />
        <MetricCard label={t('analysis.metric.wallets')} value={fmtNum(metrics?.unique_wallets)} />
        <MetricCard
          label={t('analysis.metric.holders')}
          value={holders ? fmtNum(holders.n_holders) : '—'}
        />
      </div>

      {/* Volume + trade-count charts */}
      {series.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="card p-5">
            <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3">
              {t('analysis.chart.volume')}
            </h3>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={series}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v) => `$${Number(v).toLocaleString()}`} />
                  <Line type="monotone" dataKey="volume" stroke="#6366f1" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="card p-5">
            <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3">
              {t('analysis.chart.trades')}
            </h3>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={series}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Bar dataKey="trades" fill="#10b981" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Concentration + holder split */}
      {(conc || holders) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {conc && (
            <div className="card p-5 space-y-2">
              <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-1">
                {t('analysis.concentration')}
              </h3>
              <ConcRow label={t('analysis.conc.top1')} value={fmtPct(conc.top1_share)} />
              <ConcRow label={t('analysis.conc.top5')} value={fmtPct(conc.top5_share)} />
              <ConcRow label={t('analysis.conc.top10')} value={fmtPct(conc.top10_share)} />
            </div>
          )}
          {holders && (
            <div className="card p-5 space-y-2">
              <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-1">
                {t('analysis.metric.holders')}
              </h3>
              <ConcRow label={t('analysis.holders.yes')} value={fmtNum(holders.yes_holders)} />
              <ConcRow label={t('analysis.holders.no')} value={fmtNum(holders.no_holders)} />
            </div>
          )}
        </div>
      )}

      {/* Top wallets */}
      {topWallets.length > 0 && (
        <div className="card p-5">
          <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3">
            {t('analysis.topWallets')}
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-surface-400 border-b border-surface-200 dark:border-surface-700">
                  <th className="py-2 pr-3 font-medium">{t('analysis.col.wallet')}</th>
                  <th className="py-2 pr-3 font-medium text-right">{t('analysis.col.notional')}</th>
                  <th className="py-2 font-medium text-right">{t('analysis.col.share')}</th>
                </tr>
              </thead>
              <tbody>
                {topWallets.map((w) => (
                  <tr key={w.wallet} className="border-b border-surface-100 dark:border-surface-800 last:border-0">
                    <td className="py-2 pr-3">
                      <code className="text-xs text-surface-600 dark:text-surface-300">
                        {w.wallet.slice(0, 8)}…{w.wallet.slice(-6)}
                      </code>
                    </td>
                    <td className="py-2 pr-3 text-right text-surface-700 dark:text-surface-200">
                      ${w.notional.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                    <td className="py-2 text-right text-surface-500">
                      {(w.share * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-surface-400">{label}</div>
      <div className="text-xl font-bold text-surface-900 dark:text-white mt-1">{value}</div>
    </div>
  );
}

function ConcRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-surface-500 dark:text-surface-400">{label}</span>
      <span className="font-medium text-surface-800 dark:text-surface-100">{value}</span>
    </div>
  );
}
