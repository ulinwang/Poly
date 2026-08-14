import { NavLink, Route, Routes } from 'react-router-dom';
import {
  ChevronDown, Database, Pencil, RefreshCw,
  Save, Settings2, SlidersHorizontal, TestTube, X,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useSettingsStore } from '../stores';
import { api } from '../lib/api';
import { useI18n } from '../lib/i18n';
import type { ApiSettings, ProviderInfo } from '../types';

type SettingsSection = 'models' | 'general';

interface SettingsProps {
  modal?: boolean;
  onClose?: () => void;
}

export default function Settings({ modal = false, onClose }: SettingsProps) {
  const { t } = useI18n();
  const [section, setSection] = useState<SettingsSection>('models');

  useEffect(() => {
    if (!modal) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [modal, onClose]);

  const shell = (
    <div className={`flex overflow-hidden rounded-[22px] border border-surface-200/90 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.18)] dark:border-white/8 dark:bg-surface-900 ${modal ? 'h-[min(800px,calc(100vh-48px))] flex-col' : 'flex-col'}`}>
      <header className="flex items-center justify-between border-b border-surface-200 px-6 py-5 dark:border-white/8">
        <h1 className={`${modal ? 'text-xl' : 'text-2xl'} font-bold tracking-tight text-surface-950 dark:text-white`}>{t('settings.title')}</h1>
        {modal && (
          <button type="button" onClick={onClose} className="grid h-9 w-9 place-items-center rounded-xl text-surface-400 transition hover:bg-surface-100 hover:text-surface-900 dark:hover:bg-white/5 dark:hover:text-white" aria-label={t('settings.close')}>
            <X className="h-5 w-5" />
          </button>
        )}
      </header>

      <div className={`grid min-h-0 flex-1 md:grid-cols-[220px_minmax(0,1fr)] ${modal ? '' : 'min-h-[640px]'}`}>
        <aside className="border-b border-surface-200 p-3 dark:border-white/8 md:border-b-0 md:border-r">
          <div className="flex gap-1 overflow-x-auto md:flex-col">
            {modal ? (
              <>
                <ModalSettingsTab active={section === 'general'} onClick={() => setSection('general')} icon={<Settings2 className="h-4 w-4" />} label={t('settings.tab.general')} />
                <ModalSettingsTab active={section === 'models'} onClick={() => setSection('models')} icon={<Database className="h-4 w-4" />} label={t('settings.tab.models')} />
              </>
            ) : (
              <>
                <SettingsTab to="/settings/general" icon={<Settings2 className="h-4 w-4" />} label={t('settings.tab.general')} />
                <SettingsTab to="/settings/models" icon={<Database className="h-4 w-4" />} label={t('settings.tab.models')} />
              </>
            )}
          </div>
        </aside>

        <section className="min-w-0 overflow-y-auto p-5 sm:p-7">
          {modal ? (
            section === 'models' ? <ModelSettings /> : <GeneralSettings />
          ) : (
            <Routes>
              <Route path="general" element={<GeneralSettings />} />
              <Route path="models" element={<ModelSettings />} />
              <Route path="api" element={<ModelSettings />} />
              <Route path="keys" element={<ModelSettings />} />
              <Route path="*" element={<ModelSettings />} />
            </Routes>
          )}
        </section>
      </div>
    </div>
  );

  if (modal) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-surface-950/35 p-4 backdrop-blur-[3px] sm:p-6" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose?.(); }}>
        <div role="dialog" aria-modal="true" aria-label={t('settings.title')} className="w-full max-w-6xl">
          {shell}
        </div>
      </div>
    );
  }

  return <div className="mx-auto max-w-6xl">{shell}</div>;
}

function ModalSettingsTab({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button type="button" onClick={onClick} className={`flex shrink-0 items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium transition-colors ${active ? 'bg-surface-100 text-surface-950 dark:bg-white/10 dark:text-white' : 'text-surface-600 hover:bg-surface-100/70 dark:text-surface-300 dark:hover:bg-white/5'}`}>
      {icon}
      {label}
    </button>
  );
}

function SettingsTab({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <NavLink to={to} className={({ isActive }) => `flex shrink-0 items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium transition-colors ${isActive ? 'bg-surface-100 text-surface-950 dark:bg-white/10 dark:text-white' : 'text-surface-600 hover:bg-surface-100/70 dark:text-surface-300 dark:hover:bg-white/5'}`}>
      {icon}
      {label}
    </NavLink>
  );
}

function ModelSettings() {
  const { t } = useI18n();
  const apiSettings = useSettingsStore((state) => state.apiSettings);
  const setApiSettings = useSettingsStore((state) => state.setApiSettings);
  const updateApiSettings = useSettingsStore((state) => state.updateApiSettings);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [liveModels, setLiveModels] = useState<string[] | null>(null);
  const [modelsSource, setModelsSource] = useState<string | null>(null);
  const [refreshingModels, setRefreshingModels] = useState(false);
  const [providersError, setProvidersError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [snapshot, setSnapshot] = useState<ApiSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testOk, setTestOk] = useState<boolean | null>(null);

  useEffect(() => {
    api.listProviders()
      .then((response) => setProviders(response.providers))
      .catch((error) => setProvidersError((error as Error).message));
    api.getApiSettings()
      .then((response) => {
        const settings = response.settings;
        setApiSettings({
          provider: settings.provider,
          model: settings.model,
          base_url: settings.base_url,
          temperature: settings.temperature,
          max_tokens: settings.max_tokens,
          request_timeout_seconds: settings.request_timeout_seconds,
          max_retries: settings.max_retries,
          api_key: '',
          api_key_set: settings.api_key_set,
        });
      })
      .catch(() => { /* keep local defaults */ });
  }, [setApiSettings]);

  const provider = providers.find((item) => item.id === apiSettings.provider);
  const models = liveModels ?? provider?.models ?? [];
  const providerName = provider?.name || apiSettings.provider || t('settings.models.notConfigured');

  const refreshModels = useCallback(async () => {
    if (!apiSettings.provider) return;
    setRefreshingModels(true);
    setModelsSource(null);
    try {
      const response = await api.discoverProviderModels({
        provider: apiSettings.provider,
        base_url: apiSettings.base_url || undefined,
        api_key: apiSettings.api_key?.trim() || undefined,
      });
      setLiveModels(response.models);
      setModelsSource(response.source === 'live'
        ? t('settings.api.modelsLive', { count: response.models.length })
        : t('settings.api.modelsCatalog', { suffix: response.message ? `: ${response.message}` : '' }));
    } catch (error) {
      setModelsSource(t('settings.api.modelsFailed', { msg: (error as Error).message }));
    } finally {
      setRefreshingModels(false);
    }
  }, [apiSettings.provider, apiSettings.base_url, apiSettings.api_key, t]);

  const beginEditing = (custom = false) => {
    setSnapshot({ ...apiSettings });
    if (custom) {
      const customProvider = providers.find((item) => item.id === 'custom');
      updateApiSettings({ provider: customProvider?.id || 'custom', model: '', base_url: '' });
    }
    setEditing(true);
  };

  const cancelEditing = () => {
    if (snapshot) setApiSettings(snapshot);
    setEditing(false);
    setTestResult(null);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const { api_key, ...rest } = apiSettings;
      const payload = api_key?.trim() ? { ...rest, api_key: api_key.trim() } : rest;
      const response = await api.updateApiSettings(payload as ApiSettings);
      setApiSettings({ ...response.settings, api_key: '' });
      setTestOk(true);
      setTestResult(t('settings.api.saved'));
      setEditing(false);
    } catch (error) {
      setTestOk(false);
      setTestResult(t('settings.api.saveFailed', { msg: (error as Error).message }));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTestOk(null);
    setTestResult(t('settings.api.testing'));
    try {
      const response = await api.testConnection(apiSettings);
      setTestOk(response.ok);
      setTestResult(response.ok ? t('settings.api.testOk') : t('settings.api.testFailed', { msg: response.message }));
    } catch (error) {
      setTestOk(false);
      setTestResult(t('settings.api.testFailed', { msg: (error as Error).message }));
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <h2 className="text-xl font-bold tracking-tight text-surface-950 dark:text-white">{t('settings.models.title')}</h2>
        <p className="mt-2 text-sm text-surface-500 dark:text-surface-400">{t('settings.models.subtitle')}</p>
      </header>

      <section className="flex items-center justify-between gap-4 rounded-2xl border border-surface-200 px-5 py-4 dark:border-white/10">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-base font-semibold text-surface-950 dark:text-white">{providerName}</h3>
            <span className={`h-2 w-2 rounded-full ${apiSettings.api_key_set ? 'bg-success' : 'bg-surface-300'}`} />
          </div>
          <p className="mt-1 truncate text-xs text-surface-400">{apiSettings.model || t('settings.models.noModel')}</p>
        </div>
        <button type="button" onClick={() => beginEditing()} className="btn-secondary flex shrink-0 items-center gap-2">
          <Pencil className="h-3.5 w-3.5" />
          {t('settings.models.edit')}
        </button>
      </section>

      {!editing ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" onClick={() => beginEditing()} className="rounded-2xl border border-dashed border-surface-300 bg-surface-50/70 px-5 py-5 text-sm font-medium text-surface-700 transition hover:border-surface-400 hover:bg-surface-100 dark:border-white/15 dark:bg-white/[0.025] dark:text-surface-200">
            + {t('settings.models.addProvider')}
          </button>
          <button type="button" onClick={() => beginEditing(true)} className="rounded-2xl border border-dashed border-surface-300 px-5 py-5 text-sm font-medium text-surface-700 transition hover:border-surface-400 hover:bg-surface-50 dark:border-white/15 dark:text-surface-200 dark:hover:bg-white/[0.025]">
            + {t('settings.models.customProvider')}
          </button>
        </div>
      ) : (
        <section className="space-y-5 rounded-2xl bg-[#f6f7f7] p-5 dark:bg-white/[0.035] sm:p-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-2 text-sm font-medium text-surface-600 dark:text-surface-300">
              <span>{t('settings.api.provider')}</span>
              <select value={apiSettings.provider} onChange={(event) => {
                const next = providers.find((item) => item.id === event.target.value);
                setLiveModels(null);
                setModelsSource(null);
                updateApiSettings({ provider: event.target.value, model: next?.models[0] || '', base_url: next?.base_url || '' });
              }} className="input bg-white dark:bg-surface-900">
                {providers.length === 0 && <option value={apiSettings.provider}>{apiSettings.provider}</option>}
                {providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            <label className="space-y-2 text-sm font-medium text-surface-600 dark:text-surface-300">
              <span className="flex items-center justify-between"><span>{t('settings.api.apiKey')}</span><span className={`text-xs font-normal ${apiSettings.api_key_set ? 'text-success' : 'text-surface-400'}`}>{apiSettings.api_key_set ? t('settings.api.keySet') : t('settings.api.keyUnset')}</span></span>
              <input type="password" value={apiSettings.api_key || ''} onChange={(event) => updateApiSettings({ api_key: event.target.value })} placeholder={apiSettings.api_key_set ? t('settings.api.keyPlaceholderSet') : 'sk-...'} className="input bg-white dark:bg-surface-900" />
            </label>
          </div>

          <details className="group border-t border-surface-200 pt-4 dark:border-white/10" open={Boolean(provider?.requires_base_url || apiSettings.base_url)}>
            <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-surface-700 dark:text-surface-200">
              <ChevronDown className="h-4 w-4 transition group-open:rotate-180" />
              {t('settings.models.customSettings')}
            </summary>
            <label className="mt-4 block space-y-2 text-sm font-medium text-surface-600 dark:text-surface-300">
              <span>{t('settings.api.baseUrl')}</span>
              <input type="url" value={apiSettings.base_url || ''} onChange={(event) => updateApiSettings({ base_url: event.target.value })} placeholder={provider?.base_url || 'https://api.example.com/v1'} className="input bg-white dark:bg-surface-900" />
            </label>
          </details>

          <div className="border-t border-surface-200 pt-4 dark:border-white/10">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h4 className="text-sm font-semibold text-surface-700 dark:text-surface-200">{t('settings.models.catalog')}</h4>
                <p className="mt-0.5 text-xs text-surface-400">{modelsSource || t('settings.models.catalogHint')}</p>
              </div>
              <button type="button" onClick={() => void refreshModels()} disabled={refreshingModels} className="flex shrink-0 items-center gap-1.5 text-xs font-semibold text-primary-600 disabled:opacity-50">
                <RefreshCw className={`h-3.5 w-3.5 ${refreshingModels ? 'animate-spin' : ''}`} />
                {t('settings.models.fetchModels')}
              </button>
            </div>
            <input type="text" list="model-options" value={apiSettings.model} onChange={(event) => updateApiSettings({ model: event.target.value })} placeholder={t('settings.api.modelPlaceholder')} className="input mt-3 bg-white dark:bg-surface-900" />
            <datalist id="model-options">{models.map((model) => <option key={model} value={model} />)}</datalist>
          </div>

          <details className="group border-t border-surface-200 pt-4 dark:border-white/10">
            <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-surface-700 dark:text-surface-200">
              <SlidersHorizontal className="h-4 w-4" />
              {t('settings.api.generation')}
            </summary>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <label className="space-y-2 text-xs text-surface-500"><span>{t('settings.api.temperature', { value: apiSettings.temperature })}</span><input type="range" min="0" max="2" step="0.1" value={apiSettings.temperature} onChange={(event) => updateApiSettings({ temperature: Number(event.target.value) })} className="w-full" /></label>
              <label className="space-y-2 text-xs text-surface-500"><span>{t('settings.api.maxTokens', { value: apiSettings.max_tokens })}</span><input type="range" min="256" max="32768" step="256" value={apiSettings.max_tokens} onChange={(event) => updateApiSettings({ max_tokens: Number(event.target.value) })} className="w-full" /></label>
              <label className="space-y-2 text-xs text-surface-500"><span>{t('settings.api.timeout')}</span><input type="number" min="5" max="600" value={apiSettings.request_timeout_seconds} onChange={(event) => updateApiSettings({ request_timeout_seconds: Number(event.target.value) })} className="input bg-white dark:bg-surface-900" /></label>
              <label className="space-y-2 text-xs text-surface-500"><span>{t('settings.api.retries')}</span><input type="number" min="1" max="10" value={apiSettings.max_retries} onChange={(event) => updateApiSettings({ max_retries: Number(event.target.value) })} className="input bg-white dark:bg-surface-900" /></label>
            </div>
          </details>

          {providersError && <p className="text-sm text-danger">{providersError}</p>}
          {testResult && <p className={`text-sm ${testOk === false ? 'text-danger' : testOk === true ? 'text-success' : 'text-surface-500'}`}>{testResult}</p>}

          <div className="flex flex-wrap justify-end gap-3 border-t border-surface-200 pt-4 dark:border-white/10">
            <button type="button" onClick={handleTest} className="btn-secondary flex items-center gap-2"><TestTube className="h-4 w-4" />{t('settings.api.testConnection')}</button>
            <button type="button" onClick={cancelEditing} className="btn-secondary">{t('settings.models.cancel')}</button>
            <button type="button" onClick={handleSave} disabled={saving} className="btn-primary flex items-center gap-2"><Save className="h-4 w-4" />{saving ? t('settings.api.saving') : t('settings.api.save')}</button>
          </div>
        </section>
      )}
    </div>
  );
}

function GeneralSettings() {
  const { t, locale, setLocale } = useI18n();
  const darkMode = useSettingsStore((state) => state.darkMode);
  const toggleDarkMode = useSettingsStore((state) => state.toggleDarkMode);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <h2 className="text-xl font-bold tracking-tight text-surface-950 dark:text-white">{t('settings.general.heading')}</h2>
      </header>
      <section className="overflow-hidden rounded-2xl border border-surface-200 px-5 dark:border-white/8">
        <div className="flex items-center justify-between gap-5 border-b border-surface-200 py-5 dark:border-white/8">
          <div><div className="text-sm font-medium text-surface-700 dark:text-surface-300">{t('settings.general.language')}</div><div className="text-xs text-surface-400">{t('settings.general.languageHint')}</div></div>
          <div className="flex items-center gap-1 rounded-lg bg-surface-100 p-1 dark:bg-surface-800">
            <button onClick={() => setLocale('zh')} className={`rounded-md px-3 py-1 text-sm transition-colors ${locale === 'zh' ? 'bg-white font-medium text-primary-600 shadow-sm dark:bg-surface-700' : 'text-surface-500'}`}>{t('lang.zh')}</button>
            <button onClick={() => setLocale('en')} className={`rounded-md px-3 py-1 text-sm transition-colors ${locale === 'en' ? 'bg-white font-medium text-primary-600 shadow-sm dark:bg-surface-700' : 'text-surface-500'}`}>{t('lang.en')}</button>
          </div>
        </div>
        <div className="flex items-center justify-between gap-5 py-5">
          <div><div className="text-sm font-medium text-surface-700 dark:text-surface-300">{t('settings.general.darkMode')}</div><div className="text-xs text-surface-400">{t('settings.general.darkModeHint')}</div></div>
          <button onClick={toggleDarkMode} className={`relative h-6 w-12 rounded-full transition-colors ${darkMode ? 'bg-primary-600' : 'bg-surface-300 dark:bg-surface-600'}`} aria-label={t('settings.general.darkMode')}>
            <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${darkMode ? 'translate-x-6' : 'translate-x-0.5'}`} />
          </button>
        </div>
      </section>
    </div>
  );
}
