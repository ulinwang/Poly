import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { ShieldCheck } from 'lucide-react';
import { api } from '../lib/api';
import { clearApiToken, getApiToken, setApiToken } from '../lib/auth';
import { useI18n } from '../lib/i18n';

type GateState = 'loading' | 'locked' | 'unlocked';

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const [state, setState] = useState<GateState>('loading');
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    const initialize = async () => {
      try {
        const config = await api.getAuthConfig();
        if (!config.required) {
          if (active) setState('unlocked');
          return;
        }
        const storedToken = getApiToken();
        if (!storedToken) {
          if (active) setState('locked');
          return;
        }
        await api.verifyAuthentication();
        if (active) setState('unlocked');
      } catch {
        clearApiToken();
        if (active) setState('locked');
      }
    };
    void initialize();
    return () => {
      active = false;
    };
  }, []);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const candidate = token.trim();
    if (!candidate) return;
    setSubmitting(true);
    setError('');
    setApiToken(candidate);
    try {
      await api.verifyAuthentication();
      setToken('');
      setState('unlocked');
    } catch {
      clearApiToken();
      setError(t('auth.invalid'));
    } finally {
      setSubmitting(false);
    }
  };

  if (state === 'loading') {
    return (
      <div className="flex items-center justify-center h-screen bg-surface-50 dark:bg-surface-950">
        <div className="w-12 h-12 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (state === 'unlocked') return children;

  return (
    <main className="min-h-screen flex items-center justify-center bg-surface-50 dark:bg-surface-950 p-6">
      <form onSubmit={handleSubmit} className="card w-full max-w-md p-8 space-y-6">
        <div className="w-12 h-12 rounded-2xl bg-primary-100 dark:bg-primary-900/40 flex items-center justify-center">
          <ShieldCheck className="w-6 h-6 text-primary-600 dark:text-primary-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-surface-900 dark:text-white">
            {t('auth.title')}
          </h1>
          <p className="mt-2 text-sm text-surface-500 dark:text-surface-400">
            {t('auth.subtitle')}
          </p>
        </div>
        <input
          autoFocus
          type="password"
          autoComplete="current-password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder={t('auth.tokenPlaceholder')}
          className="input"
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <button
          type="submit"
          disabled={submitting || !token.trim()}
          className="btn-primary w-full"
        >
          {submitting ? t('auth.verifying') : t('auth.unlock')}
        </button>
        <p className="text-xs text-surface-400">{t('auth.sessionHint')}</p>
      </form>
    </main>
  );
}
