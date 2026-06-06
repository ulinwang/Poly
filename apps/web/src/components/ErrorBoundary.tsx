import { Component, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';
import { useSettingsStore } from '../stores';
import { translate } from '../lib/i18n';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info);
  }

  render() {
    if (this.state.hasError) {
      // Class component can't use hooks; read the persisted locale directly.
      const locale = useSettingsStore.getState().locale;
      const t = (key: string) => translate(locale, key);
      return (
        <div className="flex flex-col items-center justify-center h-screen px-4 text-center">
          <AlertTriangle className="w-12 h-12 text-warning mb-4" />
          <h2 className="text-lg font-semibold text-surface-900 dark:text-white mb-2">
            {t('error.title')}
          </h2>
          <p className="text-sm text-surface-500 max-w-md mb-4">
            {this.state.error?.message || t('error.unexpected')}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="btn-primary"
          >
            {t('error.reload')}
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
