import { useEffect, useState } from 'react';
import { Bot, FileText, Wrench, X } from 'lucide-react';
import { api } from '../lib/api';
import { useI18n } from '../lib/i18n';
import type { AgentInfo as AgentInfoData, AgentTool, AgentPromptTemplate } from '../types';

type Tab = 'prompts' | 'tools';

export default function AgentInfo() {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>('prompts');
  const [data, setData] = useState<AgentInfoData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Detail shown in a modal after clicking a grid card.
  const [selectedTool, setSelectedTool] = useState<AgentTool | null>(null);
  const [selectedPrompt, setSelectedPrompt] = useState<AgentPromptTemplate | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.getAgentInfo()
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const tools = data?.tools ?? [];
  const templateEntries = Object.entries(data?.prompt_templates ?? {});

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Bot className="w-6 h-6 text-primary-600" />
        <div>
          <h1 className="text-xl font-bold text-surface-900 dark:text-white">{t('agent.title')}</h1>
          <p className="text-sm text-surface-400 mt-0.5">{t('agent.subtitle')}</p>
        </div>
      </div>

      {/* Top tab switcher */}
      <div className="flex gap-1 border-b border-surface-200 dark:border-surface-700">
        <TabButton active={tab === 'prompts'} onClick={() => setTab('prompts')}
          icon={<FileText className="w-4 h-4" />} label={t('agent.tab.prompts')} />
        <TabButton active={tab === 'tools'} onClick={() => setTab('tools')}
          icon={<Wrench className="w-4 h-4" />} label={t('agent.tab.tools')} />
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16">
          <div className="w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {!loading && error && (
        <div className="card p-6 text-sm text-danger">{t('agent.loadFailed', { msg: error })}</div>
      )}

      {!loading && !error && (
        <>
          {tab === 'tools' && (
            <div className="space-y-4">
              <p className="text-sm text-surface-400">{t('agent.tools.count', { count: tools.length })}</p>
              {tools.length === 0 ? (
                <div className="card p-6 text-sm text-surface-400">{t('agent.empty')}</div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {tools.map((tool) => (
                    <ToolGridCard key={tool.name} tool={tool} onClick={() => setSelectedTool(tool)} />
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === 'prompts' && (
            <div className="space-y-4">
              <p className="text-sm text-surface-400">{t('agent.prompts.count', { count: templateEntries.length })}</p>
              {templateEntries.length === 0 ? (
                <div className="card p-6 text-sm text-surface-400">{t('agent.empty')}</div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {templateEntries.map(([key, tpl]) => (
                    <PromptGridCard key={key} tpl={tpl} onClick={() => setSelectedPrompt(tpl)} />
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {selectedTool && (
        <DetailModal title={selectedTool.name} mono onClose={() => setSelectedTool(null)}>
          <ToolDetail tool={selectedTool} />
        </DetailModal>
      )}
      {selectedPrompt && (
        <DetailModal title={selectedPrompt.title} onClose={() => setSelectedPrompt(null)}>
          <PromptDetail tpl={selectedPrompt} />
        </DetailModal>
      )}
    </div>
  );
}

function TabButton({ active, onClick, icon, label }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; label: string;
}) {
  return (
    <button type="button" onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
        active ? 'border-primary-500 text-primary-600'
               : 'border-transparent text-surface-500 hover:text-surface-700 dark:hover:text-surface-300'
      }`}>
      {icon}
      {label}
    </button>
  );
}

// ─────────────────────────── grid cards (title + metadata) ───────────────────

function ToolGridCard({ tool, onClick }: { tool: AgentTool; onClick: () => void }) {
  const { t } = useI18n();
  const nParams = Object.keys(tool.parameters?.properties ?? {}).length;
  return (
    <button type="button" onClick={onClick}
      className="card p-4 text-left hover:shadow-md hover:border-primary-300 dark:hover:border-primary-700 transition-all flex flex-col gap-2 h-full">
      <code className="text-sm font-semibold text-primary-600 dark:text-primary-300 break-all">{tool.name}</code>
      <p className="text-xs text-surface-500 dark:text-surface-400 line-clamp-2 flex-1">{tool.description}</p>
      <span className="text-[10px] text-surface-400">
        {nParams} {t('agent.tools.params')}
      </span>
    </button>
  );
}

function PromptGridCard({ tpl, onClick }: { tpl: AgentPromptTemplate; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className="card p-4 text-left hover:shadow-md hover:border-primary-300 dark:hover:border-primary-700 transition-all flex flex-col gap-2 h-full">
      <h3 className="text-sm font-semibold text-surface-800 dark:text-surface-100">{tpl.title}</h3>
      {tpl.description && (
        <p className="text-xs text-surface-500 dark:text-surface-400 line-clamp-2 flex-1">{tpl.description}</p>
      )}
      {tpl.source && (
        <code className="text-[10px] text-surface-400 break-all">{tpl.source}</code>
      )}
    </button>
  );
}

// ─────────────────────────── detail modal + bodies ──────────────────────────

function DetailModal({ title, mono, onClose, children }: {
  title: string; mono?: boolean; onClose: () => void; children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative card w-full max-w-2xl max-h-[85vh] overflow-y-auto p-6 z-10">
        <div className="flex items-start justify-between gap-4 mb-4">
          <h2 className={`text-lg font-bold text-surface-900 dark:text-white ${mono ? 'font-mono' : ''}`}>{title}</h2>
          <button type="button" onClick={onClose}
            className="p-1.5 rounded-lg text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-700 flex-shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ToolDetail({ tool }: { tool: AgentTool }) {
  const { t } = useI18n();
  const props = tool.parameters?.properties ?? {};
  const required = new Set(tool.parameters?.required ?? []);
  const paramNames = Object.keys(props);
  return (
    <div className="space-y-4">
      <p className="text-sm text-surface-600 dark:text-surface-300">{tool.description}</p>
      <div>
        <div className="text-xs font-semibold text-surface-500 uppercase tracking-wide mb-2">
          {t('agent.tools.params')}
        </div>
        {paramNames.length === 0 ? (
          <p className="text-xs text-surface-400">{t('agent.tools.noParams')}</p>
        ) : (
          <div className="space-y-2">
            {paramNames.map((name) => {
              const p = props[name];
              return (
                <div key={name} className="rounded-lg border border-surface-200 dark:border-surface-700 px-3 py-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <code className="text-xs font-medium text-surface-800 dark:text-surface-100">{name}</code>
                    {p?.type && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-100 dark:bg-surface-700 text-surface-500">{p.type}</span>
                    )}
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      required.has(name) ? 'bg-danger/10 text-danger' : 'bg-surface-100 dark:bg-surface-700 text-surface-400'
                    }`}>
                      {required.has(name) ? t('agent.tools.required') : t('agent.tools.optional')}
                    </span>
                  </div>
                  {p?.description && (
                    <p className="text-xs text-surface-500 dark:text-surface-400 mt-1">{p.description}</p>
                  )}
                  {p?.enum && p.enum.length > 0 && (
                    <p className="text-[11px] text-surface-400 mt-1">{t('agent.tools.enum')}: {p.enum.join(', ')}</p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function PromptDetail({ tpl }: { tpl: AgentPromptTemplate }) {
  const { t } = useI18n();
  return (
    <div className="space-y-3">
      {tpl.description && (
        <p className="text-sm text-surface-500 dark:text-surface-400">{tpl.description}</p>
      )}
      {tpl.source && (
        <p className="text-xs text-surface-400">{t('agent.prompts.source')}: <code>{tpl.source}</code></p>
      )}
      <pre className="text-xs leading-relaxed bg-surface-50 dark:bg-surface-900 border border-surface-200 dark:border-surface-700 rounded-lg p-4 overflow-x-auto whitespace-pre-wrap font-mono text-surface-700 dark:text-surface-300">
        {tpl.template}
      </pre>
    </div>
  );
}
