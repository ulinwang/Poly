import { useLocation } from 'react-router-dom';
import {
  LayoutGrid, FlaskConical, Bot, BarChart3, Settings,
  PanelLeftClose, PanelLeftOpen, Moon, Sun, Languages,
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
      className={`${collapsed ? 'w-16' : 'w-56'} h-full flex flex-col flex-shrink-0
        bg-white dark:bg-surface-800 border-r border-surface-200 dark:border-surface-700
        transition-[width] duration-200`}
    >
      {/* Collapse toggle */}
      <div className={`flex items-center h-14 px-3 ${collapsed ? 'justify-center' : 'justify-end'}`}>
        <button
          onClick={toggleSidebar}
          title={collapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')}
          className="p-2 rounded-lg text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-700/60 transition-colors"
        >
          {collapsed ? <PanelLeftOpen className="w-5 h-5" /> : <PanelLeftClose className="w-5 h-5" />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 space-y-1">
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
                px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                active
                  ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300 shadow-sm'
                  : 'text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-700/60 hover:text-surface-900 dark:hover:text-surface-200'
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
      <div className="px-2 pb-3 border-t border-surface-200 dark:border-surface-700 pt-2 space-y-1">
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
      </div>
    </aside>
  );
}
