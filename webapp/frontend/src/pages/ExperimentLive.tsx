import { useParams } from 'react-router-dom';
import { useEffect, useState, useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart, Pie, Cell, Legend,
} from 'recharts';
import { Square, ArrowLeft, TrendingUp, Users } from 'lucide-react';
import { api } from '../lib/api';
import { useExperimentStore } from '../stores';
import { useSSE, useFormatNumber } from '../hooks';

export default function ExperimentLive() {
  const { id } = useParams<{ id: string }>();
  const [experiment, setExperiment] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const metrics = useExperimentStore((s) => s.metrics);
  const decisions = useExperimentStore((s) => s.decisions);
  const tickLog = useExperimentStore((s) => s.tickLog);
  const running = useExperimentStore((s) => s.running);
  const error = useExperimentStore((s) => s.error);
  const resetSimulation = useExperimentStore((s) => s.resetSimulation);

  const formatNumber = useFormatNumber();

  // Connect SSE
  useSSE(id || null);

  useEffect(() => {
    if (!id) return;
    resetSimulation();
    setLoading(true);
    api.getExperiment(id)
      .then((res) => setExperiment(res.experiment))
      .catch((err) => console.error('Failed to load experiment:', err))
      .finally(() => setLoading(false));
  }, [id, resetSimulation]);

  const handleCancel = () => {
    if (!id) return;
    api.cancelExperiment(id).catch(console.error);
  };

  if (loading) {
    return <div className="text-center py-20 text-surface-400">Loading experiment...</div>;
  }

  const chartData = metrics.yesMidHistory.map((v, i) => ({ tick: i, value: v }));

  // Compute derived stats
  const summary = experiment?.result_summary as Record<string, unknown> | undefined;
  const pnlData = useMemo(() => {
    const pnl = summary?.pnl as Record<string, number> | undefined;
    if (!pnl) return [];
    return Object.entries(pnl).map(([agent_id, value]) => ({ agent_id: `A${agent_id}`, value }));
  }, [summary]);

  const decisionTypeData = useMemo(() => {
    const counts: Record<string, number> = {};
    decisions.forEach((d) => {
      const key = d.order_type || 'unknown';
      counts[key] = (counts[key] || 0) + 1;
    });
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [decisions]);

  const PIE_COLORS = ['#0d9488', '#f59e0b', '#ef4444', '#6366f1', '#8b5cf6', '#ec4899'];

  const isDone = experiment?.status === 'completed' || experiment?.status === 'cancelled' || experiment?.status === 'error';

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
              <span className={`badge ${running ? 'badge-live' : 'badge-resolved'}`}>
                {running ? 'Running' : experiment?.status || 'Done'}
              </span>
              <span>{experiment?.n_agents} agents · {experiment?.n_ticks} ticks</span>
            </div>
          </div>
        </div>
        {running && (
          <button onClick={handleCancel} className="btn-secondary flex items-center gap-2 text-danger">
            <Square className="w-4 h-4" />
            Cancel
          </button>
        )}
      </div>

      {error && (
        <div className="card p-4 bg-danger/10 border-danger/20 text-danger text-sm">
          Error: {error}
        </div>
      )}

      {/* Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="YES Mid" value={metrics.yesMid.toFixed(3)} />
        <MetricCard label="Fills" value={formatNumber(metrics.nFills)} />
        <MetricCard label="Actions" value={formatNumber(metrics.nActions)} />
        <MetricCard label="Tick Time" value={`${metrics.lastTickElapsed.toFixed(1)}s`} />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Price History */}
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3">
            YES Price History
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="tick" tick={{ fontSize: 12 }} />
                <YAxis domain={[0, 1]} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#0d9488"
                  strokeWidth={2}
                  dot={false}
                  fill="rgba(13, 148, 136, 0.1)"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* PnL Distribution (completed experiments only) */}
        {isDone && pnlData.length > 0 && (
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              Agent PnL Distribution
            </h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pnlData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="agent_id" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}`} />
                  <Bar dataKey="value">
                    {pnlData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.value >= 0 ? '#0d9488' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Decision Type Distribution */}
        {decisionTypeData.length > 0 && (
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3 flex items-center gap-2">
              <Users className="w-4 h-4" />
              Decision Types
            </h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={decisionTypeData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={4}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}
                  >
                    {decisionTypeData.map((_entry, index) => (
                      <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>

      {/* Two columns: decisions + tick log */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {/* Agent Decisions */}
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3">
            Agent Decisions ({decisions.length})
          </h3>
          <div className="space-y-2 max-h-80 xl:max-h-96 overflow-y-auto">
            {decisions.length === 0 ? (
              <div className="text-center py-8 text-surface-400 text-sm">
                Waiting for agent decisions...
              </div>
            ) : (
              [...decisions].reverse().map((d) => (
                <div
                  key={d.id}
                  className="p-3 rounded-lg bg-surface-50 dark:bg-surface-800/50 text-sm"
                >
                  <div className="flex items-center gap-2 text-xs text-surface-500 flex-wrap">
                    <span className="font-mono">A{d.agent_id}</span>
                    <span className="badge bg-surface-200 text-surface-600">{d.persona_type}</span>
                    <span>t{d.tick + 1}</span>
                    <span className="ml-auto">{d.api_latency_ms}ms</span>
                  </div>
                  <div className="mt-1 font-medium text-surface-800 dark:text-surface-200">
                    {d.order_type}
                    {d.side && ` ${d.side} ${d.outcome}`}
                    {d.price > 0 && ` @ ${d.price.toFixed(3)}`}
                    {d.size_usd > 0 && ` · $${formatNumber(d.size_usd)}`}
                  </div>
                  {d.reasoning && (
                    <p className="mt-1 text-xs text-surface-500 line-clamp-2">{d.reasoning}</p>
                  )}
                  {d.api_error && (
                    <p className="mt-1 text-xs text-danger">{d.api_error}</p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Tick Log */}
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-3">
            Tick Log
          </h3>
          <div className="space-y-1 max-h-80 xl:max-h-96 overflow-y-auto font-mono text-xs">
            {tickLog.length === 0 ? (
              <div className="text-center py-8 text-surface-400">
                Simulation events will appear here...
              </div>
            ) : (
              [...tickLog].reverse().map((entry) => (
                <div
                  key={entry.id}
                  className={`flex gap-2 px-2 py-1 rounded ${
                    entry.kind === 'error' ? 'bg-danger/10 text-danger' :
                    entry.kind === 'warn' ? 'bg-warning/10 text-warning' :
                    'text-surface-600 dark:text-surface-400'
                  }`}
                >
                  <span className="text-surface-400 whitespace-nowrap">{entry.time}</span>
                  <span className="font-semibold whitespace-nowrap min-w-[60px]">{entry.label}</span>
                  <span className="truncate">{entry.msg}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
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
