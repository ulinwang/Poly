import { useState, useEffect } from 'react';
import { Search, Menu, Zap } from 'lucide-react';
import { useMarketStore } from '../../stores';
import { useDebounce } from '../../hooks';

export default function TopNav({ onMenuClick }: { onMenuClick?: () => void }) {
  const [searchInput, setSearchInput] = useState('');
  const setSearchQuery = useMarketStore((s) => s.setSearchQuery);
  const debouncedSearch = useDebounce(searchInput, 300);

  useEffect(() => {
    setSearchQuery(debouncedSearch);
  }, [debouncedSearch, setSearchQuery]);

  return (
    <header className="sticky top-0 z-50 bg-white dark:bg-surface-900 border-b border-surface-200 dark:border-surface-700">
      <div className="flex items-center h-14 px-4 lg:px-6 gap-4">
        {/* Left: mobile menu + logo */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <button
            onClick={onMenuClick}
            className="p-2 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-800 lg:hidden"
            aria-label="打开菜单"
          >
            <Menu className="w-5 h-5 text-surface-600 dark:text-surface-400" />
          </button>
          <a href="#/markets" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <span className="text-lg font-bold text-surface-900 dark:text-white hidden sm:block">
              Poly
            </span>
          </a>
        </div>

        {/* Center: Search */}
        <div className="flex-1 max-w-2xl">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="搜索市场…"
              className="w-full pl-9 pr-4 py-2 bg-surface-100 dark:bg-surface-800 border-0 rounded-xl text-sm text-surface-900 dark:text-surface-100 placeholder:text-surface-400 focus:ring-2 focus:ring-primary-500 focus:outline-none"
            />
          </div>
        </div>
      </div>
    </header>
  );
}
