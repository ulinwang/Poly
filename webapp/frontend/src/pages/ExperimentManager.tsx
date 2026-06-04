import { useEffect, useState, useCallback } from 'react';
import {
  FlaskConical, Clock, CheckCircle, XCircle, AlertCircle,
  RefreshCw, Search, ChevronLeft, ChevronRight, Filter,
} from 'lucide-react';
import { api } from '../lib/api';
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

const PAGE_SIZE = 20;

export default function ExperimentManager() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listExperiments({
        status: statusFilter || undefined,
        slug: searchQuery || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setExperiments(res.experiments);
      setTotal(res.total);
    } catch (err) {
      setError('Failed to load experiments: ' + (err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, searchQuery, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FlaskConical className="w-5 h-5 text-primary-600" />
          <h1 className="text-xl font-bold text-surface-900 dark:text-white">Experiments</h1>
          <span className="text-sm text-surface-400">({total})</span>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="p-2 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
          title="Refresh"
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
            onChange={(e) => { setSearchQuery(e.target.value); setOffset(0); }}
            placeholder="Search by slug..."
            className="input pl-9 w-full"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-surface-400" />
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
            className="input py-2"
          >
            <option value="">All Status</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
            <option value="error">Error</option>
          </select>
        </div>
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
            {searchQuery || statusFilter ? 'No matching experiments.' : 'No experiments yet.'}
          </p>
          <p className="text-sm text-surface-400 mt-1">
            Select a market and start a simulation to see it here.
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
                      {exp.status}
                    </span>
                  </div>
                  <div className="text-xs text-surface-400 mt-0.5">
                    {exp.n_agents} agents · {exp.n_ticks} ticks · {exp.persona_set}
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
                Page {currentPage} of {totalPages}
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
