import { useState } from 'react';
import { Search, Settings, Menu, Zap } from 'lucide-react';
import { useMarketStore, useSettingsStore } from '../../stores';
import { useDebounce } from '../../hooks';

export default function TopNav() {
  const [searchInput, setSearchInput] = useState('');
  const [showSettings, setShowSettings] = useState(false);

  const setSearchQuery = useMarketStore((s) => s.setSearchQuery);
  const toggleSidebar = useSettingsStore((s) => s.toggleSidebar);
  const darkMode = useSettingsStore((s) => s.darkMode);
  const toggleDarkMode = useSettingsStore((s) => s.toggleDarkMode);

  const debouncedSearch = useDebounce(searchInput, 300);

  // Update store when debounced value changes
  useState(() => {
    setSearchQuery(debouncedSearch);
  });

  return (
    <header className="sticky top-0 z-50 bg-white/80 dark:bg-surface-900/80 backdrop-blur-md border-b border-surface-200 dark:border-surface-700">
      <div className="flex items-center justify-between h-14 px-4 lg:px-6">
        {/* Left: Logo + brand */}
        <div className="flex items-center gap-3">
          <button
            onClick={toggleSidebar}
            className="p-2 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-800 lg:hidden"
          >
            <Menu className="w-5 h-5 text-surface-600 dark:text-surface-400" />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-primary-600 flex items-center justify-center">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <span className="text-lg font-bold text-surface-900 dark:text-white hidden sm:block">
              PolyMetl
            </span>
          </div>
        </div>

        {/* Center: Search */}
        <div className="flex-1 max-w-xl mx-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search markets..."
              className="w-full pl-9 pr-4 py-2 bg-surface-100 dark:bg-surface-800 border-0 rounded-xl text-sm focus:ring-2 focus:ring-primary-500 focus:outline-none"
            />
          </div>
        </div>

        {/* Right: Settings */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-800 relative"
          >
            <Settings className="w-5 h-5 text-surface-600 dark:text-surface-400" />
          </button>

          {/* Settings dropdown */}
          {showSettings && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowSettings(false)}
              />
              <div className="absolute right-4 top-14 z-50 w-56 bg-white dark:bg-surface-800 rounded-xl shadow-lg border border-surface-200 dark:border-surface-700 py-2">
                <div className="px-4 py-2 text-sm font-medium text-surface-500 dark:text-surface-400">
                  Settings
                </div>
                <button
                  onClick={() => {
                    toggleDarkMode();
                    setShowSettings(false);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-surface-50 dark:hover:bg-surface-700"
                >
                  {darkMode ? '☀️ Light Mode' : '🌙 Dark Mode'}
                </button>
                <a
                  href="#/settings/api"
                  onClick={() => setShowSettings(false)}
                  className="block w-full px-4 py-2 text-left text-sm hover:bg-surface-50 dark:hover:bg-surface-700"
                >
                  ⚙️ API Configuration
                </a>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
