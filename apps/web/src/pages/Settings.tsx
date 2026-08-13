import { Routes, Route, NavLink } from 'react-router-dom';
import {
  Activity, CheckCircle2, Key, KeyRound, Palette, Plus, RefreshCw,
  Save, Server, SlidersHorizontal, TestTube, Trash2,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useSettingsStore } from '../stores';
import { api } from '../lib/api';
import { useI18n } from '../lib/i18n';
import type { ApiKey, ProviderInfo } from '../types';

export default function Settings() {
  const { t } = useI18n();
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-primary-600">Workspace</p>
        <h1 className="mt-1 text-3xl font-extrabold tracking-tight text-surface-900 dark:text-white">{t('settings.title')}</h1>
      </div>

      <div className="flex gap-1 border-b border-surface-200 dark:border-surface-700">
        <SettingsTab to="/settings/api" icon={<Key className="w-4 h-4" />} label={t('settings.tab.api')} />
        <SettingsTab to="/settings/keys" icon={<KeyRound className="w-4 h-4" />} label={t('settings.tab.keys')} />
        <SettingsTab to="/settings/general" icon={<Palette className="w-4 h-4" />} label={t('settings.tab.general')} />
      </div>

      <Routes>
        <Route path="api" element={<APISettings />} />
        <Route path="keys" element={<KeysSettings />} />
        <Route path="general" element={<GeneralSettings />} />
      </Routes>
    </div>
  );
}

function SettingsTab({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
          isActive
            ? 'border-primary-500 text-primary-600'
            : 'border-transparent text-surface-500 hover:text-surface-700 dark:hover:text-surface-300'
        }`
      }
    >
      {icon}
      {label}
    </NavLink>
  );
}

function APISettings() {
  const { t } = useI18n();
  const apiSettings = useSettingsStore((s) => s.apiSettings);
  const updateApiSettings = useSettingsStore((s) => s.updateApiSettings);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  // Track whether the current result is a success (drives color) independently
  // of the (now localized) message text.
  const [testOk, setTestOk] = useState<boolean | null>(null);
  // Provider catalog comes from the backend (single source of truth, litellm).
  const [providers, setProviders] = useState<import('../types').ProviderInfo[]>([]);
  // Live model list fetched via the provider's /models endpoint. When set, it
  // overrides the static catalog suggestions for the current provider. Cleared
  // when the provider changes (see onChange below).
  const [liveModels, setLiveModels] = useState<string[] | null>(null);
  const [modelsSource, setModelsSource] = useState<string | null>(null);
  const [refreshingModels, setRefreshingModels] = useState(false);
  const [refreshingProviders, setRefreshingProviders] = useState(false);
  const [providersError, setProvidersError] = useState<string | null>(null);

  const loadProviders = useCallback(async () => {
    setRefreshingProviders(true);
    setProvidersError(null);
    try {
      const res = await api.listProviders();
      setProviders(res.providers);
    } catch (error) {
      setProvidersError((error as Error).message);
    } finally {
      setRefreshingProviders(false);
    }
  }, []);

  useEffect(() => { void loadProviders(); }, [loadProviders]);

  // Load stored settings (without plaintext key) so we can show whether a key
  // is configured. The api_key input stays empty / user-controlled.
  useEffect(() => {
    api
      .getApiSettings()
      .then((res) => {
        const s = res.settings;
        updateApiSettings({
          provider: s.provider,
          model: s.model,
          base_url: s.base_url,
          temperature: s.temperature,
          max_tokens: s.max_tokens,
          request_timeout_seconds: s.request_timeout_seconds,
          max_retries: s.max_retries,
          api_key_set: s.api_key_set,
        });
      })
      .catch(() => {
        /* keep defaults on failure */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const provider = providers.find((p) => p.id === apiSettings.provider);
  // Live models (if fetched) take precedence over the static catalog list.
  const models = liveModels ?? provider?.models ?? [];

  const handleRefreshModels = useCallback(async () => {
    setRefreshingModels(true);
    setModelsSource(null);
    try {
      const res = await api.discoverProviderModels({
        provider: apiSettings.provider,
        base_url: apiSettings.base_url || undefined,
        api_key: apiSettings.api_key?.trim() || undefined,
      });
      setLiveModels(res.models);
      setModelsSource(
        res.source === 'live'
          ? t('settings.api.modelsLive', { count: res.models.length })
          : t('settings.api.modelsCatalog', { suffix: res.message ? `: ${res.message}` : '' }),
      );
    } catch (err) {
      setModelsSource(t('settings.api.modelsFailed', { msg: (err as Error).message }));
    } finally {
      setRefreshingModels(false);
    }
  }, [apiSettings.provider, apiSettings.base_url, apiSettings.api_key, t]);

  // Debounced live discovery: selecting a provider or changing the key/base
  // URL refreshes its models without forcing the user to save first.
  useEffect(() => {
    if (!apiSettings.provider) return;
    const timer = window.setTimeout(() => { void handleRefreshModels(); }, 450);
    return () => window.clearTimeout(timer);
  }, [apiSettings.provider, apiSettings.base_url, apiSettings.api_key, handleRefreshModels]);

  const handleSave = async () => {
    setSaving(true);
    try {
      // Only include the plaintext api_key when the user actually entered one;
      // otherwise omit it so the server keeps the existing stored key.
      const { api_key, ...rest } = apiSettings;
      const payload = api_key && api_key.length > 0 ? { ...rest, api_key } : rest;
      const res = await api.updateApiSettings(payload as typeof apiSettings);
      // Reflect server's view (api_key_set) and clear the local key input.
      updateApiSettings({ api_key: '', api_key_set: res.settings.api_key_set });
      setTestOk(true);
      setTestResult(t('settings.api.saved'));
      setTimeout(() => setTestResult(null), 3000);
    } catch (err) {
      setTestOk(false);
      setTestResult(t('settings.api.saveFailed', { msg: (err as Error).message }));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTestOk(null);
    setTestResult(t('settings.api.testing'));
    try {
      const res = await api.testConnection(apiSettings);
      setTestOk(res.ok);
      setTestResult(res.ok ? t('settings.api.testOk') : t('settings.api.testFailed', { msg: res.message }));
      setTimeout(() => setTestResult(null), 5000);
    } catch (err) {
      setTestOk(false);
      setTestResult(t('settings.api.testFailed', { msg: (err as Error).message }));
      setTimeout(() => setTestResult(null), 5000);
    }
  };

  return (
    <div className="space-y-5">
      <section className="overflow-hidden rounded-3xl border border-primary-100 bg-gradient-to-br from-primary-50 via-white to-cyan-50 p-6 dark:border-primary-900/60 dark:from-primary-950/50 dark:via-surface-900 dark:to-cyan-950/30">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-primary-700 dark:text-primary-300"><Activity className="h-4 w-4" /><span className="text-xs font-bold uppercase tracking-[0.14em]">{t('settings.api.liveDiscovery')}</span></div>
            <h2 className="text-xl font-bold text-surface-900 dark:text-white">{t('settings.api.heading')}</h2>
            <p className="mt-1 text-sm text-surface-500 dark:text-surface-400">{t('settings.api.liveDiscoveryHint')}</p>
          </div>
          <button type="button" onClick={() => void loadProviders()} disabled={refreshingProviders} className="btn-secondary flex items-center justify-center gap-2">
            <RefreshCw className={`h-4 w-4 ${refreshingProviders ? 'animate-spin' : ''}`} />
            {t('settings.api.refreshProviders')}
          </button>
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-5">
        <section className="card space-y-5 p-6 lg:col-span-3">
          <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary-50 text-primary-700 dark:bg-primary-950 dark:text-primary-300"><Server className="h-5 w-5" /></span><div><h3 className="font-semibold text-surface-900 dark:text-white">{t('settings.api.connection')}</h3><p className="text-xs text-surface-400">{t('settings.api.subtitle')}</p></div></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium text-surface-700 dark:text-surface-300">{t('settings.api.provider')}</label>
              <select value={apiSettings.provider} onChange={(e) => { const next = providers.find((item) => item.id === e.target.value); setLiveModels(null); setModelsSource(null); updateApiSettings({ provider: e.target.value, model: next?.models[0] || '', base_url: next?.base_url || '' }); }} className="input">
                {providers.length === 0 && <option value={apiSettings.provider}>{apiSettings.provider}</option>}
                {providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
              {providersError && <p className="text-xs text-danger">{providersError}</p>}
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between"><label className="text-sm font-medium text-surface-700 dark:text-surface-300">{t('settings.api.model')}</label><button type="button" onClick={() => void handleRefreshModels()} disabled={refreshingModels} className="flex items-center gap-1 text-xs font-semibold text-primary-600 disabled:opacity-50"><RefreshCw className={`h-3.5 w-3.5 ${refreshingModels ? 'animate-spin' : ''}`} />{refreshingModels ? t('settings.api.refreshingModels') : t('settings.api.refreshModels')}</button></div>
              <input type="text" list="model-options" value={apiSettings.model} onChange={(e) => updateApiSettings({ model: e.target.value })} placeholder={t('settings.api.modelPlaceholder')} className="input" />
              <datalist id="model-options">{models.map((model) => <option key={model} value={model} />)}</datalist>
              {modelsSource && <p className="text-xs text-surface-400">{modelsSource}</p>}
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between"><label className="text-sm font-medium text-surface-700 dark:text-surface-300">{t('settings.api.apiKey')}</label><span className={`inline-flex items-center gap-1 text-xs ${apiSettings.api_key_set ? 'text-success' : 'text-surface-400'}`}>{apiSettings.api_key_set && <CheckCircle2 className="h-3.5 w-3.5" />}{apiSettings.api_key_set ? t('settings.api.keySet') : t('settings.api.keyUnset')}</span></div>
            <input type="password" value={apiSettings.api_key || ''} onChange={(e) => updateApiSettings({ api_key: e.target.value })} placeholder={apiSettings.api_key_set ? t('settings.api.keyPlaceholderSet') : 'sk-...'} className="input" />
            <p className="text-xs text-surface-400">{t('settings.api.keyHint')}</p>
          </div>
          {(provider?.base_url || provider?.requires_base_url || apiSettings.base_url) && <div className="space-y-2"><label className="text-sm font-medium text-surface-700 dark:text-surface-300">{t('settings.api.baseUrl')}</label><input type="url" value={apiSettings.base_url || ''} onChange={(e) => updateApiSettings({ base_url: e.target.value })} placeholder={provider?.base_url || 'https://api.example.com/v1'} className="input" /></div>}
        </section>

        <section className="card space-y-5 p-6 lg:col-span-2">
          <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300"><SlidersHorizontal className="h-5 w-5" /></span><h3 className="font-semibold text-surface-900 dark:text-white">{t('settings.api.generation')}</h3></div>
          <div className="space-y-2"><label className="text-sm font-medium text-surface-700 dark:text-surface-300">{t('settings.api.temperature', { value: apiSettings.temperature })}</label><input type="range" min="0" max="2" step="0.1" value={apiSettings.temperature} onChange={(e) => updateApiSettings({ temperature: Number(e.target.value) })} className="w-full" /><div className="flex justify-between text-xs text-surface-400"><span>{t('settings.api.deterministic')}</span><span>{t('settings.api.creative')}</span></div></div>
          <div className="space-y-2"><label className="text-sm font-medium text-surface-700 dark:text-surface-300">{t('settings.api.maxTokens', { value: apiSettings.max_tokens })}</label><input type="range" min="256" max="32768" step="256" value={apiSettings.max_tokens} onChange={(e) => updateApiSettings({ max_tokens: Number(e.target.value) })} className="w-full" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2"><label className="text-sm font-medium text-surface-700 dark:text-surface-300">{t('settings.api.timeout')}</label><input type="number" min="5" max="600" value={apiSettings.request_timeout_seconds} onChange={(e) => updateApiSettings({ request_timeout_seconds: Number(e.target.value) })} className="input" /><p className="text-xs text-surface-400">{t('settings.api.timeoutHint')}</p></div>
            <div className="space-y-2"><label className="text-sm font-medium text-surface-700 dark:text-surface-300">{t('settings.api.retries')}</label><input type="number" min="1" max="10" value={apiSettings.max_retries} onChange={(e) => updateApiSettings({ max_retries: Number(e.target.value) })} className="input" /><p className="text-xs text-surface-400">{t('settings.api.retriesHint')}</p></div>
          </div>
        </section>
      </div>

      <div className="card flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <button onClick={handleSave} disabled={saving} className="btn-primary flex items-center gap-2">
          <Save className="w-4 h-4" />
          {saving ? t('settings.api.saving') : t('settings.api.save')}
        </button>
        <button onClick={handleTest} className="btn-secondary flex items-center gap-2">
          <TestTube className="w-4 h-4" />
          {t('settings.api.testConnection')}
        </button>
        {testResult && (
          <span className={`text-sm sm:ml-auto ${testOk === false ? 'text-danger' : testOk === true ? 'text-success' : 'text-surface-400'}`}>
            {testResult}
          </span>
        )}
      </div>
    </div>
  );
}

function KeysSettings() {
  const { t } = useI18n();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [name, setName] = useState('');
  const [provider, setProvider] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listApiKeys()
      .then((res) => setKeys(res.keys))
      .catch(() => { /* keep empty list on failure */ });
    api.listProviders()
      .then((res) => {
        setProviders(res.providers);
        if (res.providers.length > 0) setProvider((p) => p || res.providers[0].id);
      })
      .catch(() => { /* dropdown stays empty */ });
  }, []);

  const selectedProvider = providers.find((p) => p.id === provider);

  const handleAdd = async () => {
    setError(null);
    if (!name.trim()) { setError(t('settings.keys.errName')); return; }
    if (!provider) { setError(t('settings.keys.errProvider')); return; }
    if (!apiKey.trim()) { setError(t('settings.keys.errKey')); return; }
    setSaving(true);
    try {
      const res = await api.createApiKey({
        name: name.trim(),
        provider,
        api_key: apiKey.trim(),
        base_url: baseUrl.trim() || undefined,
        model: model.trim() || undefined,
      });
      setKeys(res.keys);
      // Reset the form (keep the chosen provider for quick repeat entry).
      setName('');
      setApiKey('');
      setBaseUrl('');
      setModel('');
    } catch (err) {
      setError(t('settings.keys.saveFailed', { msg: (err as Error).message }));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      const res = await api.deleteApiKey(id);
      setKeys(res.keys);
    } catch (err) {
      setError(t('settings.keys.deleteFailed', { msg: (err as Error).message }));
    }
  };

  return (
    <div className="card p-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-surface-800 dark:text-surface-100">
          {t('settings.keys.heading')}
        </h2>
        <p className="text-sm text-surface-400 mt-1">
          {t('settings.keys.subtitle')}
        </p>
      </div>

      {/* Stored keys */}
      <div className="space-y-2">
        {keys.length === 0 ? (
          <p className="text-sm text-surface-400">{t('settings.keys.none')}</p>
        ) : (
          keys.map((k) => (
            <div
              key={k.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-surface-200 dark:border-surface-700 px-3 py-2"
            >
              <div className="min-w-0">
                <div className="text-sm font-medium text-surface-800 dark:text-surface-100 truncate">
                  {k.name}
                </div>
                <div className="text-xs text-surface-400 truncate">
                  {k.provider} · {k.key_masked}
                  {k.model ? ` · ${k.model}` : ''}
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleDelete(k.id)}
                className="flex items-center gap-1 text-xs text-danger hover:opacity-80"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t('settings.keys.delete')}
              </button>
            </div>
          ))
        )}
      </div>

      {/* Add new key */}
      <div className="space-y-3 pt-4 border-t border-surface-200 dark:border-surface-700">
        <h3 className="text-sm font-semibold text-surface-700 dark:text-surface-300">
          {t('settings.keys.add')}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-surface-500 mb-1">{t('settings.keys.name')}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('settings.keys.namePlaceholder')}
              className="input"
            />
          </div>
          <div>
            <label className="block text-xs text-surface-500 mb-1">{t('settings.keys.provider')}</label>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="input"
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className="block text-xs text-surface-500 mb-1">{t('settings.api.apiKey')}</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              className="input"
            />
          </div>
          <div>
            <label className="block text-xs text-surface-500 mb-1">
              {t('settings.keys.baseUrlOptional')}
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={selectedProvider?.base_url || 'https://api.example.com/v1'}
              className="input"
            />
          </div>
          <div>
            <label className="block text-xs text-surface-500 mb-1">
              {t('settings.keys.modelOptional')}
            </label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={selectedProvider?.models[0] || 'model id'}
              className="input"
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleAdd}
            disabled={saving}
            className="btn-primary flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            {saving ? t('settings.keys.adding') : t('settings.keys.addButton')}
          </button>
          {error && <span className="text-sm text-danger">{error}</span>}
        </div>
      </div>
    </div>
  );
}

function GeneralSettings() {
  const { t, locale, setLocale } = useI18n();
  const darkMode = useSettingsStore((s) => s.darkMode);
  const toggleDarkMode = useSettingsStore((s) => s.toggleDarkMode);

  return (
    <div className="card p-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-surface-800 dark:text-surface-100">
          {t('settings.general.heading')}
        </h2>
      </div>

      {/* Language */}
      <div className="flex items-center justify-between py-3 border-b border-surface-200 dark:border-surface-700">
        <div>
          <div className="text-sm font-medium text-surface-700 dark:text-surface-300">
            {t('settings.general.language')}
          </div>
          <div className="text-xs text-surface-400">
            {t('settings.general.languageHint')}
          </div>
        </div>
        <div className="flex items-center gap-1 rounded-lg bg-surface-100 dark:bg-surface-800 p-1">
          <button
            onClick={() => setLocale('zh')}
            className={`px-3 py-1 text-sm rounded-md transition-colors ${
              locale === 'zh'
                ? 'bg-white dark:bg-surface-700 text-primary-600 shadow-sm font-medium'
                : 'text-surface-500 hover:text-surface-700 dark:hover:text-surface-300'
            }`}
          >
            {t('lang.zh')}
          </button>
          <button
            onClick={() => setLocale('en')}
            className={`px-3 py-1 text-sm rounded-md transition-colors ${
              locale === 'en'
                ? 'bg-white dark:bg-surface-700 text-primary-600 shadow-sm font-medium'
                : 'text-surface-500 hover:text-surface-700 dark:hover:text-surface-300'
            }`}
          >
            {t('lang.en')}
          </button>
        </div>
      </div>

      {/* Dark mode */}
      <div className="flex items-center justify-between py-3 border-b border-surface-200 dark:border-surface-700">
        <div>
          <div className="text-sm font-medium text-surface-700 dark:text-surface-300">
            {t('settings.general.darkMode')}
          </div>
          <div className="text-xs text-surface-400">
            {t('settings.general.darkModeHint')}
          </div>
        </div>
        <button
          onClick={toggleDarkMode}
          className={`relative w-12 h-6 rounded-full transition-colors ${
            darkMode ? 'bg-primary-600' : 'bg-surface-300 dark:bg-surface-600'
          }`}
        >
          <div
            className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
              darkMode ? 'translate-x-6' : 'translate-x-0.5'
            }`}
          />
        </button>
      </div>
    </div>
  );
}
