import { useLocation } from 'react-router-dom';
import {
  LayoutGrid, FlaskConical, Bot, BarChart3, Settings,
  PanelLeftClose, PanelLeftOpen, Moon, Sun, Languages, Orbit,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useExperimentStore, useSettingsStore } from '../../stores';
import { useI18n } from '../../lib/i18n';

interface NavEntry {
  labelKey: string;
  href: string;
  icon: LucideIcon;
  /** route prefix used to decide the active state */
  match: string;
}

const NAV: NavEntry[] = [
  { labelKey: 'nav.browse', href: '#/markets', icon: LayoutGrid, match: '/markets' },
  { labelKey: 'nav.experiments', href: '#/experiments', icon: FlaskConical, match: '/experiments' },
  { labelKey: 'nav.agent', href: '#/agent', icon: Bot, match: '/agent' },
  { labelKey: 'nav.analysis', href: '#/analysis', icon: BarChart3, match: '/analysis' },
];

interface SidebarProps {
  /** called after navigating — used to close the mobile drawer */
  onNavigate?: () => void;
  /** opens settings without leaving the current workspace page */
  onOpenSettings?: () => void;
  settingsOpen?: boolean;
  /** mobile drawers should always render the full navigation */
  forceExpanded?: boolean;
}

export default function Sidebar({ onNavigate, onOpenSettings, settingsOpen = false, forceExpanded = false }: SidebarProps) {
  const location = useLocation();
  const collapsed = useSettingsStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useSettingsStore((s) => s.toggleSidebar);
  const darkMode = useSettingsStore((s) => s.darkMode);
  const toggleDarkMode = useSettingsStore((s) => s.toggleDarkMode);
  const experiments = useExperimentStore((s) => s.experiments);
  const { t, locale, setLocale } = useI18n();
  const isCollapsed = forceExpanded ? false : collapsed;

  const runningCount = experiments.filter((e) => e.status === 'running').length;

  return (
    <aside
      className={`${isCollapsed ? 'w-[68px]' : 'w-[248px]'} h-full flex flex-col flex-shrink-0
        border-r border-surface-200/80 bg-[#f7f8f8]
        transition-[width] duration-200 dark:border-white/5 dark:bg-[#101514]`}
    >
      <div className={`flex h-[68px] items-center px-4 ${isCollapsed ? 'justify-center' : 'justify-between gap-3'}`}>
        {!isCollapsed && (
          <a href="#/markets" className="flex min-w-0 items-center gap-3" onClick={onNavigate}>
            <span className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-xl bg-surface-950 text-white shadow-sm dark:bg-white dark:text-surface-950">
              <Orbit className="h-[19px] w-[19px]" />
            </span>
            <span className="min-w-0">
              <span className="block text-[17px] font-extrabold tracking-[-0.03em] text-surface-900 dark:text-white">{t('app.name')}</span>
              <span className="block truncate text-[9px] font-semibold uppercase tracking-[0.18em] text-surface-400">Agent market lab</span>
            </span>
          </a>
        )}
        <button
          onClick={forceExpanded ? onNavigate : toggleSidebar}
          className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg text-surface-400 hover:bg-surface-200/70 hover:text-surface-700 dark:hover:bg-white/5"
          title={isCollapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')}
        >
          {isCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {!isCollapsed && <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-surface-400">Workspace</p>}
        {NAV.map((item) => {
          const active = location.pathname.startsWith(item.match);
          const Icon = item.icon;
          const showBadge = item.match === '/experiments' && runningCount > 0;
          const label = t(item.labelKey);
          return (
            <a
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              title={isCollapsed ? label : undefined}
              className={`group relative flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'}
                min-h-10 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                active
                  ? 'bg-white text-surface-950 shadow-[0_5px_16px_rgba(15,23,42,0.08)] ring-1 ring-surface-200/70 dark:bg-white/10 dark:text-white dark:ring-white/10'
                  : 'text-surface-500 hover:bg-surface-200/55 hover:text-surface-900 dark:text-surface-400 dark:hover:bg-white/5 dark:hover:text-white'
              }`}
            >
              <span className="relative flex-shrink-0">
                <Icon className="w-5 h-5" />
                {showBadge && (
                  <span className="absolute -top-1.5 -right-1.5 min-w-4 h-4 px-1 bg-success text-white
                    text-[10px] font-semibold rounded-full flex items-center justify-center shadow-sm">
                    {runningCount}
                  </span>
                )}
              </span>
              {!isCollapsed && <span className="flex-1">{label}</span>}

              {/* tooltip when collapsed */}
              {isCollapsed && (
                <span className="absolute left-full ml-2 px-2.5 py-1.5 bg-surface-800 dark:bg-surface-700 text-white text-xs
                  rounded-lg opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-lg">
                  {label}
                </span>
              )}
            </a>
          );
        })}
      </nav>

      {/* Bottom: language switcher + dark mode toggle */}
      <div className="space-y-1 border-t border-surface-200/70 px-3 py-3 dark:border-white/5">
        <button
          type="button"
          onClick={() => { onNavigate?.(); onOpenSettings?.(); }}
          title={isCollapsed ? t('nav.settings') : undefined}
          className={`relative flex min-h-10 w-full items-center rounded-lg px-3 py-2 text-sm font-medium transition-all ${isCollapsed ? 'justify-center' : 'gap-3'} ${
            settingsOpen || location.pathname.startsWith('/settings')
              ? 'bg-white text-surface-950 shadow-[0_5px_16px_rgba(15,23,42,0.08)] ring-1 ring-surface-200/70 dark:bg-white/10 dark:text-white dark:ring-white/10'
              : 'text-surface-500 hover:bg-surface-200/55 hover:text-surface-900 dark:text-surface-400 dark:hover:bg-white/5 dark:hover:text-white'
          }`}
        >
          <Settings className="h-5 w-5" />
          {!isCollapsed && <span>{t('nav.settings')}</span>}
        </button>
        <div className={`flex ${isCollapsed ? 'flex-col' : ''} gap-1`}>
        <button
          onClick={() => setLocale(locale === 'zh' ? 'en' : 'zh')}
          title={t('lang.label')}
          className={`flex items-center justify-center gap-2 rounded-lg p-2 text-xs font-medium text-surface-500 hover:bg-surface-200/60 hover:text-surface-900 dark:text-surface-400 dark:hover:bg-white/5 ${isCollapsed ? 'w-full' : 'flex-1'}`}
        >
          <Languages className="w-5 h-5 flex-shrink-0" />
          {!isCollapsed && <span>{locale === 'zh' ? 'EN' : '中'}</span>}
        </button>
        <button
          onClick={toggleDarkMode}
          title={darkMode ? t('theme.light') : t('theme.dark')}
          className={`flex items-center justify-center gap-2 rounded-lg p-2 text-xs font-medium text-surface-500 hover:bg-surface-200/60 hover:text-surface-900 dark:text-surface-400 dark:hover:bg-white/5 ${isCollapsed ? 'w-full' : 'flex-1'}`}
        >
          {darkMode ? <Sun className="w-5 h-5 flex-shrink-0" /> : <Moon className="w-5 h-5 flex-shrink-0" />}
          {!isCollapsed && <span>{darkMode ? t('theme.light') : t('theme.dark')}</span>}
        </button>
        </div>
      </div>
    </aside>
  );
}
