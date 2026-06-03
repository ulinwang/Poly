import { useState } from 'react';
import { ChevronDown, ChevronRight, Play, Clock, FlaskConical, Settings, Key } from 'lucide-react';
import { useExperimentStore, useSettingsStore } from '../../stores';

const statusColors: Record<string, string> = {
  running: 'bg-success/20 text-success',
  completed: 'bg-primary-100 text-primary-700',
  cancelled: 'bg-warning/20 text-warning',
  error: 'bg-danger/20 text-danger',
  queued: 'bg-surface-200 text-surface-600',
};

export default function Sidebar() {
  const [experimentsOpen, setExperimentsOpen] = useState(true);
  const experiments = useExperimentStore((s) => s.experiments);
  const activeId = useExperimentStore((s) => s.activeId);
  const sidebarCollapsed = useSettingsStore((s) => s.sidebarCollapsed);

  const runningCount = experiments.filter((e) => e.status === 'running').length;

  if (sidebarCollapsed) {
    return (
      <aside className="w-14 bg-surface-0 dark:bg-surface-800 border-r border-surface-200 dark:border-surface-700 flex flex-col items-center py-3 gap-2">
        <SidebarIcon icon={<FlaskConical className="w-5 h-5" />} label="Experiments" count={runningCount} />
        <SidebarIcon icon={<Key className="w-5 h-5" />} label="API" />
        <SidebarIcon icon={<Settings className="w-5 h-5" />} label="Settings" />
      </aside>
    );
  }

  return (
    <aside className="w-64 bg-surface-0 dark:bg-surface-800 border-r border-surface-200 dark:border-surface-700 flex flex-col h-full overflow-hidden">
      {/* Experiments Section */}
      <div className="flex-1 overflow-y-auto">
        <button
          onClick={() => setExperimentsOpen(!experimentsOpen)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-50 dark:hover:bg-surface-700/50"
        >
          <div className="flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-surface-500" />
            <span className="text-sm font-semibold text-surface-700 dark:text-surface-300">
              Experiments
            </span>
            {runningCount > 0 && (
              <span className="badge bg-success/10 text-success text-xs">
                {runningCount}
              </span>
            )}
          </div>
          {experimentsOpen ? (
            <ChevronDown className="w-4 h-4 text-surface-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-surface-400" />
          )}
        </button>

        {experimentsOpen && (
          <div className="px-2 pb-2 space-y-1">
            {experiments.length === 0 ? (
              <div className="px-4 py-3 text-xs text-surface-400 text-center">
                No experiments yet
              </div>
            ) : (
              experiments.map((exp) => (
                <a
                  key={exp.id}
                  href={`#/experiments/${exp.id}`}
                  className={`block px-3 py-2 rounded-lg text-sm transition-colors ${
                    activeId === exp.id
                      ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                      : 'hover:bg-surface-50 dark:hover:bg-surface-700/50 text-surface-600 dark:text-surface-400'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {exp.status === 'running' ? (
                      <Play className="w-3 h-3 text-success" />
                    ) : (
                      <Clock className="w-3 h-3 text-surface-400" />
                    )}
                    <span className="truncate flex-1">{exp.slug}</span>
                    <span className={`badge text-[10px] ${statusColors[exp.status] || ''}`}>
                      {exp.status}
                    </span>
                  </div>
                  <div className="text-[10px] text-surface-400 mt-0.5 pl-5">
                    {exp.n_agents} agents · {exp.n_ticks} ticks
                  </div>
                </a>
              ))
            )}
          </div>
        )}
      </div>

      {/* Bottom: Quick API Settings */}
      <div className="border-t border-surface-200 dark:border-surface-700 p-3">
        <a
          href="#/settings/api"
          className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-surface-50 dark:hover:bg-surface-700/50 text-sm text-surface-600 dark:text-surface-400"
        >
          <Key className="w-4 h-4" />
          API Configuration
        </a>
        <a
          href="#/settings/general"
          className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-surface-50 dark:hover:bg-surface-700/50 text-sm text-surface-600 dark:text-surface-400"
        >
          <Settings className="w-4 h-4" />
          General Settings
        </a>
      </div>
    </aside>
  );
}

function SidebarIcon({ icon, label, count }: { icon: React.ReactNode; label: string; count?: number }) {
  return (
    <div className="relative p-2 rounded-lg hover:bg-surface-50 dark:hover:bg-surface-700/50 cursor-pointer group">
      {icon}
      {count !== undefined && count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-success text-white text-[10px] rounded-full flex items-center justify-center">
          {count}
        </span>
      )}
      <div className="absolute left-full ml-2 px-2 py-1 bg-surface-800 text-white text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
        {label}
      </div>
    </div>
  );
}
