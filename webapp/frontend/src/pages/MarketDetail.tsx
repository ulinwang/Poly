import { useParams } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Play, Users, Clock, ArrowLeft } from 'lucide-react';
import { api } from '../lib/api';
import { useMarketStore, useExperimentStore, useSettingsStore } from '../stores';
import type { MarketDetail as MarketDetailType } from '../types';

export default function MarketDetail() {
  const { slug } = useParams<{ slug: string }>();
  const [market, setMarket] = useState<MarketDetailType | null>(null);
  const [loading, setLoading] = useState(true);
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
    api.getMarket(slug)
      .then((res) => setMarket(res.market))
      .catch((err) => console.error('Failed to load market:', err))
      .finally(() => setLoading(false));
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
    return <div className="text-center py-20 text-surface-400">Loading market...</div>;
  }

  if (!market) {
    return <div className="text-center py-20 text-surface-400">Market not found</div>;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Back link */}
      <a href="#/markets" className="inline-flex items-center gap-1 text-sm text-surface-500 hover:text-surface-700 dark:hover:text-surface-300">
        <ArrowLeft className="w-4 h-4" />
        Back to markets
      </a>

      {/* Market Header */}
      <div className="card p-6">
        <div className="flex items-start gap-4">
          <div className={`w-14 h-14 rounded-xl flex items-center justify-center text-2xl ${
            market.is_live
              ? 'bg-primary-50 dark:bg-primary-900/30'
              : 'bg-surface-100 dark:bg-surface-700'
          }`}>
            {market.is_live ? '🟢' : '🔴'}
          </div>
          <div className="flex-1">
            <h1 className="text-xl font-bold text-surface-900 dark:text-white">
              {market.question || market.slug}
            </h1>
            <div className="flex flex-wrap gap-2 mt-2">
              <span className={`badge ${market.is_live ? 'badge-live' : 'badge-resolved'}`}>
                {market.is_live ? 'Open' : 'Resolved'}
              </span>
              <span className="badge bg-surface-100 dark:bg-surface-700 text-surface-600 dark:text-surface-400">
                tick: {market.tick_size}
              </span>
              <span className="badge bg-surface-100 dark:bg-surface-700 text-surface-600 dark:text-surface-400">
                fee: {(market.taker_fee_bps / 100).toFixed(2)}%
              </span>
            </div>
          </div>
        </div>

        {/* Simulation Config */}
        <div className="mt-6 pt-6 border-t border-surface-200 dark:border-surface-700">
          <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300 mb-4">
            Simulation Configuration
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-surface-500 mb-1">
                <Users className="w-3 h-3 inline mr-1" />
                Agents ({nAgents})
              </label>
              <input
                type="range" min="3" max="100"
                value={nAgents}
                onChange={(e) => setNAgents(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-xs text-surface-500 mb-1">
                <Clock className="w-3 h-3 inline mr-1" />
                Ticks ({nTicks})
              </label>
              <input
                type="range" min="1" max="48"
                value={nTicks}
                onChange={(e) => setNTicks(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-xs text-surface-500 mb-1">Persona Set</label>
              <select
                value={personaSet}
                onChange={(e) => setPersonaSet(e.target.value as any)}
                className="input"
              >
                <option value="archetype">Archetype (K-means)</option>
                <option value="calibrated">Calibrated (Real wallets)</option>
                <option value="no_signal">No Signal (Ablation)</option>
              </select>
            </div>
          </div>

          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={handleStart}
              disabled={starting || !market.is_live}
              className="btn-primary flex items-center gap-2"
            >
              <Play className="w-4 h-4" />
              {starting ? 'Starting...' : 'Start Simulation'}
            </button>
            {!market.is_live && (
              <span className="text-sm text-warning">
                This market is resolved and cannot be simulated.
              </span>
            )}
            <span className="text-xs text-surface-400">
              LLM: {apiSettings.provider} / {apiSettings.model}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
