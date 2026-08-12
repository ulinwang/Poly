import { useLocation } from 'react-router-dom';
import {
  LayoutGrid, FlaskConical, Bot, BarChart3, Settings,
  PanelLeftClose, PanelLeftOpen, Moon, Sun, Languages, Zap,
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
  { labelKey: 'nav.settings', href: '#/settings/api', icon: Settings, match: '/settings' },
];

interface SidebarProps {
  /** called after navigating — used to close the mobile drawer */
  onNavigate?: () => void;
}

export default function Sidebar({ onNavigate }: SidebarProps) {
  const location = useLocation();
  const collapsed = useSettingsStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useSettingsStore((s) => s.toggleSidebar);
  const darkMode = useSettingsStore((s) => s.darkMode);
  const toggleDarkMode = useSettingsStore((s) => s.toggleDarkMode);
  const experiments = useExperimentStore((s) => s.experiments);
  const { t, locale, setLocale } = useI18n();

  const runningCount = experiments.filter((e) => e.status === 'running').length;

  return (
    <aside
      className={`${collapsed ? 'w-[72px]' : 'w-64'} h-full flex flex-col flex-shrink-0
        border-r border-white/70 bg-white/82 shadow-[8px_0_30px_rgba(15,118,110,0.04)] backdrop-blur-xl
        transition-[width] duration-200 dark:border-white/5 dark:bg-[#0d1c19]/90 dark:shadow-none`}
    >
      <div className={`flex h-[76px] items-center border-b border-surface-100 px-4 dark:border-white/5 ${collapsed ? 'justify-center' : 'gap-3'}`}>
        <a href="#/markets" className="flex min-w-0 items-center gap-3" onClick={onNavigate}>
          <span className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-primary-400 via-primary-500 to-primary-700 shadow-[0_8px_22px_rgba(13,148,136,0.28)]">
            <Zap className="h-5 w-5 text-white" fill="currentColor" />
          </span>
          {!collapsed && (
            <span className="min-w-0">
              <span className="block text-lg font-extrabold tracking-[-0.03em] text-surface-900 dark:text-white">{t('app.name')}</span>
              <span className="block truncate text-[10px] font-semibold uppercase tracking-[0.18em] text-primary-600 dark:text-primary-400">Agent market lab</span>
            </span>
          )}
        </a>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1.5 px-3 py-5">
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
              title={collapsed ? label : undefined}
              className={`group relative flex items-center ${collapsed ? 'justify-center' : 'gap-3'}
                min-h-11 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                active
                  ? 'bg-primary-600 text-white shadow-[0_8px_20px_rgba(13,148,136,0.2)] dark:bg-primary-600 dark:text-white'
                  : 'text-surface-500 hover:bg-white hover:text-surface-900 hover:shadow-sm dark:text-surface-400 dark:hover:bg-white/5 dark:hover:text-white'
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
              {!collapsed && <span>{label}</span>}

              {/* tooltip when collapsed */}
              {collapsed && (
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
      <div className="space-y-1 border-t border-surface-100 px-3 py-3 dark:border-white/5">
        <button
          onClick={() => setLocale(locale === 'zh' ? 'en' : 'zh')}
          title={t('lang.label')}
          className={`w-full flex items-center ${collapsed ? 'justify-center' : 'gap-3'}
            px-3 py-2.5 rounded-xl text-sm font-medium text-surface-600 dark:text-surface-400
            hover:bg-surface-100 dark:hover:bg-surface-700/60 hover:text-surface-900 dark:hover:text-surface-200 transition-all`}
        >
          <Languages className="w-5 h-5 flex-shrink-0" />
          {!collapsed && <span>{locale === 'zh' ? t('lang.en') : t('lang.zh')}</span>}
        </button>
        <button
          onClick={toggleDarkMode}
          title={darkMode ? t('theme.light') : t('theme.dark')}
          className={`w-full flex items-center ${collapsed ? 'justify-center' : 'gap-3'}
            px-3 py-2.5 rounded-xl text-sm font-medium text-surface-600 dark:text-surface-400
            hover:bg-surface-100 dark:hover:bg-surface-700/60 hover:text-surface-900 dark:hover:text-surface-200 transition-all`}
        >
          {darkMode ? <Sun className="w-5 h-5 flex-shrink-0" /> : <Moon className="w-5 h-5 flex-shrink-0" />}
          {!collapsed && <span>{darkMode ? t('theme.light') : t('theme.dark')}</span>}
        </button>
        <button
          onClick={toggleSidebar}
          title={collapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')}
          className={`hidden w-full items-center rounded-xl px-3 py-2.5 text-sm font-medium text-surface-500 transition-all hover:bg-surface-100 hover:text-surface-900 dark:text-surface-400 dark:hover:bg-white/5 dark:hover:text-white lg:flex ${collapsed ? 'justify-center' : 'gap-3'}`}
        >
          {collapsed ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}
          {!collapsed && <span>{t('nav.collapseSidebar')}</span>}
        </button>
      </div>
    </aside>
  );
}
