import { FlaskConical, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { useExperimentStore } from '../stores';

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

export default function ExperimentManager() {
  const experiments = useExperimentStore((s) => s.experiments);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <FlaskConical className="w-5 h-5 text-primary-600" />
        <h1 className="text-xl font-bold text-surface-900 dark:text-white">Experiments</h1>
      </div>

      {experiments.length === 0 ? (
        <div className="card p-12 text-center">
          <FlaskConical className="w-12 h-12 text-surface-300 mx-auto mb-3" />
          <p className="text-surface-500 dark:text-surface-400">No experiments yet.</p>
          <p className="text-sm text-surface-400 mt-1">
            Select a market and start a simulation to see it here.
          </p>
        </div>
      ) : (
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
      )}
    </div>
  );
}
