import { Menu, Orbit } from 'lucide-react';
import { useI18n } from '../../lib/i18n';

/**
 * Mobile-only app bar. Page titles live in the page content itself so the
 * desktop workspace never renders two competing headers.
 */
export default function TopNav({ onMenuClick }: { onMenuClick?: () => void }) {
  const { t } = useI18n();

  return (
    <header className="z-20 border-b border-surface-200/80 bg-white/90 backdrop-blur-xl dark:border-white/5 dark:bg-[#0b0f0e]/90 lg:hidden">
      <div className="flex h-[60px] items-center gap-3 px-4 sm:px-6">
        <button
          type="button"
          onClick={onMenuClick}
          className="grid h-9 w-9 place-items-center rounded-xl border border-surface-200 bg-white text-surface-500 shadow-sm transition-colors hover:text-surface-900 dark:border-white/10 dark:bg-white/5 dark:text-surface-300"
          aria-label={t('nav.openMenu')}
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-surface-950 text-white dark:bg-white dark:text-surface-950">
          <Orbit className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-[16px] font-extrabold tracking-[-0.03em] text-surface-950 dark:text-white">{t('app.name')}</p>
          <p className="text-[9px] font-semibold uppercase tracking-[0.16em] text-surface-400">Agent market lab</p>
        </div>
      </div>
    </header>
  );
}
