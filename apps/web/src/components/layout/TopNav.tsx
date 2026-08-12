import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Search, Menu, Slash } from 'lucide-react';
import { useMarketStore } from '../../stores';
import { useDebounce } from '../../hooks';
import { useI18n } from '../../lib/i18n';

export default function TopNav({ onMenuClick }: { onMenuClick?: () => void }) {
  const location = useLocation();
  const [searchInput, setSearchInput] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);
  const setSearchQuery = useMarketStore((s) => s.setSearchQuery);
  const debouncedSearch = useDebounce(searchInput, 300);
  const { t } = useI18n();
  const isMarketRoute = location.pathname.startsWith('/markets');

  const pageKey = location.pathname.startsWith('/experiments')
    ? 'nav.experiments'
    : location.pathname.startsWith('/agent')
      ? 'nav.agent'
      : location.pathname.startsWith('/analysis')
        ? 'nav.analysis'
        : location.pathname.startsWith('/settings')
          ? 'nav.settings'
          : 'nav.browse';

  useEffect(() => {
    setSearchQuery(debouncedSearch);
  }, [debouncedSearch, setSearchQuery]);

  useEffect(() => {
    if (!isMarketRoute) return;
    const handleShortcut = (event: KeyboardEvent) => {
      if (event.key === '/' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleShortcut);
    return () => window.removeEventListener('keydown', handleShortcut);
  }, [isMarketRoute]);

  return (
    <header className="z-20 border-b border-white/70 bg-white/55 backdrop-blur-xl dark:border-white/5 dark:bg-[#081311]/55">
      <div className="flex h-[76px] items-center gap-4 px-4 sm:px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <button
            onClick={onMenuClick}
            className="rounded-xl border border-surface-200 bg-white p-2 text-surface-500 shadow-sm transition-colors hover:text-surface-900 dark:border-white/10 dark:bg-white/5 dark:text-surface-300 lg:hidden"
            aria-label={t('nav.openMenu')}
          >
            <Menu className="w-5 h-5 text-surface-600 dark:text-surface-400" />
          </button>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-primary-600 dark:text-primary-400">Workspace</p>
            <h1 className="truncate text-lg font-bold tracking-tight text-surface-900 dark:text-white">{t(pageKey)}</h1>
          </div>
        </div>

        {isMarketRoute && (
        <div className="ml-auto hidden w-full max-w-xl sm:block">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-400" />
            <input
              ref={searchRef}
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder={t('nav.searchMarkets')}
              className="h-11 w-full rounded-2xl border border-white bg-white/80 pl-11 pr-12 text-sm text-surface-900 shadow-[0_4px_20px_rgba(15,23,42,0.05)] outline-none transition-all placeholder:text-surface-400 focus:border-primary-300 focus:ring-4 focus:ring-primary-500/10 dark:border-white/10 dark:bg-white/5 dark:text-surface-100"
            />
            <span className="absolute right-3 top-1/2 flex -translate-y-1/2 items-center gap-0.5 rounded-md border border-surface-200 bg-surface-50 px-1.5 py-1 text-[10px] font-semibold text-surface-400 dark:border-white/10 dark:bg-white/5">
              <Slash className="h-3 w-3" />
            </span>
          </div>
        </div>
        )}
      </div>
    </header>
  );
}
