import { Routes, Route, NavLink } from 'react-router-dom';
import { Key, Palette, Save, TestTube } from 'lucide-react';
import { useState } from 'react';
import { useSettingsStore } from '../stores';
import { api } from '../lib/api';

export default function Settings() {
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-xl font-bold text-surface-900 dark:text-white">Settings</h1>

      <div className="flex gap-1 border-b border-surface-200 dark:border-surface-700">
        <SettingsTab to="/settings/api" icon={<Key className="w-4 h-4" />} label="API" />
        <SettingsTab to="/settings/general" icon={<Palette className="w-4 h-4" />} label="General" />
      </div>

      <Routes>
        <Route path="api" element={<APISettings />} />
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

const PROVIDERS = [
  { id: 'deepseek', name: 'DeepSeek', models: ['deepseek-chat', 'deepseek-reasoner'], requiresBaseUrl: false },
  { id: 'kimi', name: 'Kimi (Moonshot)', models: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'], requiresBaseUrl: false },
  { id: 'openai', name: 'OpenAI', models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'o1-preview'], requiresBaseUrl: false },
  { id: 'anthropic', name: 'Anthropic', models: ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-haiku-20240307'], requiresBaseUrl: false },
  { id: 'custom', name: 'Custom (OpenAI-compatible)', models: [], requiresBaseUrl: true },
];

function APISettings() {
  const apiSettings = useSettingsStore((s) => s.apiSettings);
  const updateApiSettings = useSettingsStore((s) => s.updateApiSettings);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const provider = PROVIDERS.find((p) => p.id === apiSettings.provider);
  const models = provider?.models || [];

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateApiSettings(apiSettings);
      setTestResult('Settings saved successfully');
      setTimeout(() => setTestResult(null), 3000);
    } catch (err) {
      setTestResult('Failed to save: ' + (err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTestResult('Testing connection...');
    try {
      const res = await api.testConnection(apiSettings);
      setTestResult(res.ok ? 'Connection successful!' : `Connection failed: ${res.message}`);
      setTimeout(() => setTestResult(null), 5000);
    } catch (err) {
      setTestResult('Connection failed: ' + (err as Error).message);
      setTimeout(() => setTestResult(null), 5000);
    }
  };

  return (
    <div className="card p-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-surface-800 dark:text-surface-100">
          LLM API Configuration
        </h2>
        <p className="text-sm text-surface-400 mt-1">
          Configure the LLM provider used for agent simulation.
        </p>
      </div>

      {/* Provider */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
          Provider
        </label>
        <select
          value={apiSettings.provider}
          onChange={(e) => {
            const p = PROVIDERS.find((p) => p.id === e.target.value);
            updateApiSettings({
              provider: e.target.value as any,
              model: p?.models[0] || '',
            });
          }}
          className="input"
        >
          {PROVIDERS.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {/* Model */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
          Model
        </label>
        <select
          value={apiSettings.model}
          onChange={(e) => updateApiSettings({ model: e.target.value })}
          className="input"
        >
          {models.length > 0 ? (
            models.map((m) => <option key={m} value={m}>{m}</option>)
          ) : (
            <option value="">Enter custom model below</option>
          )}
        </select>
        {models.length === 0 && (
          <input
            type="text"
            value={apiSettings.model}
            onChange={(e) => updateApiSettings({ model: e.target.value })}
            placeholder="e.g. gpt-4o"
            className="input mt-2"
          />
        )}
      </div>

      {/* API Key */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
          API Key
        </label>
        <input
          type="password"
          value={apiSettings.api_key}
          onChange={(e) => updateApiSettings({ api_key: e.target.value })}
          placeholder="sk-..."
          className="input"
        />
        <p className="text-xs text-surface-400">
          Your API key is stored locally and never sent to our servers except for LLM calls.
        </p>
      </div>

      {/* Base URL (for custom) */}
      {provider?.requiresBaseUrl && (
        <div className="space-y-2">
          <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
            Base URL
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
          Temperature ({apiSettings.temperature})
        </label>
        <input
          type="range"
          min="0" max="2" step="0.1"
          value={apiSettings.temperature}
          onChange={(e) => updateApiSettings({ temperature: Number(e.target.value) })}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-surface-400">
          <span>Deterministic (0)</span>
          <span>Creative (2)</span>
        </div>
      </div>

      {/* Max Tokens */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-surface-700 dark:text-surface-300">
          Max Tokens ({apiSettings.max_tokens})
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
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button onClick={handleTest} className="btn-secondary flex items-center gap-2">
          <TestTube className="w-4 h-4" />
          Test Connection
        </button>
        {testResult && (
          <span className={`text-sm ${testResult.includes('success') ? 'text-success' : 'text-danger'}`}>
            {testResult}
          </span>
        )}
      </div>
    </div>
  );
}

function GeneralSettings() {
  const darkMode = useSettingsStore((s) => s.darkMode);
  const toggleDarkMode = useSettingsStore((s) => s.toggleDarkMode);

  return (
    <div className="card p-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-surface-800 dark:text-surface-100">
          General Settings
        </h2>
      </div>

      <div className="flex items-center justify-between py-3 border-b border-surface-200 dark:border-surface-700">
        <div>
          <div className="text-sm font-medium text-surface-700 dark:text-surface-300">
            Dark Mode
          </div>
          <div className="text-xs text-surface-400">
            Toggle between light and dark theme
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
