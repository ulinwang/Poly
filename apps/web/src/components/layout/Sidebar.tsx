import { useLocation } from 'react-router-dom';
import {
  LayoutGrid, FlaskConical, Settings,
  PanelLeftClose, PanelLeftOpen, Moon, Sun,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useExperimentStore, useSettingsStore } from '../../stores';

interface NavEntry {
  label: string;
  href: string;
  icon: LucideIcon;
  /** route prefix used to decide the active state */
  match: string;
}

const NAV: NavEntry[] = [
  { label: '浏览', href: '#/markets', icon: LayoutGrid, match: '/markets' },
  { label: '实验', href: '#/experiments', icon: FlaskConical, match: '/experiments' },
  { label: '设置', href: '#/settings/api', icon: Settings, match: '/settings' },
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
          title={collapsed ? '展开侧边栏' : '收起侧边栏'}
          className="p-2 rounded-lg text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-700/60"
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
          return (
            <a
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              title={collapsed ? item.label : undefined}
              className={`group relative flex items-center ${collapsed ? 'justify-center' : 'gap-3'}
                px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                  : 'text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-700/60'
              }`}
            >
              <span className="relative flex-shrink-0">
                <Icon className="w-5 h-5" />
                {showBadge && (
                  <span className="absolute -top-1.5 -right-1.5 min-w-4 h-4 px-1 bg-success text-white
                    text-[10px] font-semibold rounded-full flex items-center justify-center">
                    {runningCount}
                  </span>
                )}
              </span>
              {!collapsed && <span>{item.label}</span>}

              {/* tooltip when collapsed */}
              {collapsed && (
                <span className="absolute left-full ml-2 px-2 py-1 bg-surface-800 text-white text-xs
                  rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
                  {item.label}
                </span>
              )}
            </a>
          );
        })}
      </nav>

      {/* Bottom: dark mode toggle */}
      <div className="px-2 pb-3 border-t border-surface-200 dark:border-surface-700 pt-2">
        <button
          onClick={toggleDarkMode}
          title={darkMode ? '浅色模式' : '深色模式'}
          className={`w-full flex items-center ${collapsed ? 'justify-center' : 'gap-3'}
            px-3 py-2.5 rounded-lg text-sm font-medium text-surface-600 dark:text-surface-400
            hover:bg-surface-100 dark:hover:bg-surface-700/60 transition-colors`}
        >
          {darkMode ? <Sun className="w-5 h-5 flex-shrink-0" /> : <Moon className="w-5 h-5 flex-shrink-0" />}
          {!collapsed && <span>{darkMode ? '浅色模式' : '深色模式'}</span>}
        </button>
      </div>
    </aside>
  );
}
