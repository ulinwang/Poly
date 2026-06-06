import { Routes, Route, NavLink } from 'react-router-dom';
import { Key, KeyRound, Palette, Plus, RefreshCw, Save, TestTube, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useSettingsStore } from '../stores';
import { api } from '../lib/api';
import { useI18n } from '../lib/i18n';
import type { ApiKey, ProviderInfo } from '../types';

export default function Settings() {
  const { t } = useI18n();
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-xl font-bold text-surface-900 dark:text-white">{t('settings.title')}</h1>

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

  useEffect(() => {
    api.listProviders()
      .then((res) => setProviders(res.providers))
      .catch(() => { /* ignore; dropdown just stays empty */ });
  }, []);

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

  const handleRefreshModels = async () => {
    setRefreshingModels(true);
    setModelsSource(null);
    try {
      const res = await api.listProviderModels(apiSettings.provider);
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
  };

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
    <div className="card p-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-surface-800 dark:text-surface-100">
          {t('settings.api.heading')}
        </h2>
        <p className="text-sm text-surface-400 mt-1">
          {t('settings.api.subtitle')}
        </p>
      </div>

      {/* Provider */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
          {t('settings.api.provider')}
        </label>
        <select
          value={apiSettings.provider}
          onChange={(e) => {
            const p = providers.find((p) => p.id === e.target.value);
            // Reset live-model state back to the catalog for the new provider.
            setLiveModels(null);
            setModelsSource(null);
            updateApiSettings({
              provider: e.target.value as import('../types').ApiSettings['provider'],
              model: p?.models[0] || '',
              // Auto-fill the OpenAI-compatible base URL; blank for custom /
              // litellm-native providers so the user/litellm supplies it.
              base_url: p?.base_url || '',
            });
          }}
          className="input"
        >
          {providers.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {/* Model */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
            {t('settings.api.model')}
          </label>
          {/* Fetch the live model list from the provider's /models endpoint. */}
          <button
            type="button"
            onClick={handleRefreshModels}
            disabled={refreshingModels}
            className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-700 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshingModels ? 'animate-spin' : ''}`} />
            {refreshingModels ? t('settings.api.refreshingModels') : t('settings.api.refreshModels')}
          </button>
        </div>
        {/* Editable combobox: suggestions from the provider catalog (or the live
            /models list once refreshed), but any model id can be typed (the
            endpoint forwards it as-is), so newer models still work. */}
        <input
          type="text"
          list="model-options"
          value={apiSettings.model}
          onChange={(e) => updateApiSettings({ model: e.target.value })}
          placeholder={t('settings.api.modelPlaceholder')}
          className="input"
        />
        <datalist id="model-options">
          {models.map((m) => <option key={m} value={m} />)}
        </datalist>
        {modelsSource && (
          <p className="text-xs text-surface-400">{modelsSource}</p>
        )}
      </div>

      {/* API Key */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
          {t('settings.api.apiKey')}
        </label>
        <div className="text-xs">
          {apiSettings.api_key_set ? (
            <span className="text-success">{t('settings.api.keySet')}</span>
          ) : (
            <span className="text-surface-400">{t('settings.api.keyUnset')}</span>
          )}
        </div>
        <input
          type="password"
          value={apiSettings.api_key || ''}
          onChange={(e) => updateApiSettings({ api_key: e.target.value })}
          placeholder={apiSettings.api_key_set ? t('settings.api.keyPlaceholderSet') : 'sk-...'}
          className="input"
        />
        <p className="text-xs text-surface-400">
          {t('settings.api.keyHint')}
        </p>
      </div>

      {/* Base URL (for custom) */}
      {provider?.requires_base_url && (
        <div className="space-y-2">
          <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
            {t('settings.api.baseUrl')}
          </label>
          <input
            type="text"
            value={apiSettings.base_url || ''}
            onChange={(e) => updateApiSettings({ base_url: e.target.value })}
            placeholder="https://api.openai.com/v1"
            className="input"
          />
        </div>
      )}

      {/* Temperature */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
          {t('settings.api.temperature', { value: apiSettings.temperature })}
        </label>
        <input
          type="range"
          min="0" max="2" step="0.1"
          value={apiSettings.temperature}
          onChange={(e) => updateApiSettings({ temperature: Number(e.target.value) })}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-surface-400">
          <span>{t('settings.api.deterministic')}</span>
          <span>{t('settings.api.creative')}</span>
        </div>
      </div>

      {/* Max Tokens */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
          {t('settings.api.maxTokens', { value: apiSettings.max_tokens })}
        </label>
        <input
          type="range"
          min="256" max="8192" step="256"
          value={apiSettings.max_tokens}
          onChange={(e) => updateApiSettings({ max_tokens: Number(e.target.value) })}
          className="w-full"
        />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-4 border-t border-surface-200 dark:border-surface-700">
        <button onClick={handleSave} disabled={saving} className="btn-primary flex items-center gap-2">
          <Save className="w-4 h-4" />
          {saving ? t('settings.api.saving') : t('settings.api.save')}
        </button>
        <button onClick={handleTest} className="btn-secondary flex items-center gap-2">
          <TestTube className="w-4 h-4" />
          {t('settings.api.testConnection')}
        </button>
        {testResult && (
          <span className={`text-sm ${testOk === false ? 'text-danger' : testOk === true ? 'text-success' : 'text-surface-400'}`}>
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
